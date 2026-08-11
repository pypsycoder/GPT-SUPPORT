"""
Агентный цикл: один агент со структурным выводом вместо цепочки узлов.

Заменяет intake → delegation → expert (3-9 вызовов LLM на ход) на один вызов.
Текст пациенту, уровень риска, намерение, следующий шаг и кандидаты в память
приходят одним структурным ответом.

Фаза инструментов из референса (``ref/agent_loop.py``) здесь не реализована —
это шаг 7. Каркас цикла оставлен: ``max_hops`` и место под ToolRegistry
обозначены, но при ``allowed_tools=None`` цикл сразу идёт в структурный финал.
Смешивать ``functions`` и ``response_format`` в одном запросе нельзя.

Второй инвариант — про деньги: ``session_id`` один на весь ход и на весь тред,
и системный промпт тоже один. Тогда со второго хода префикс берётся из кэша.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.llm import prompt_assembly
from app.llm.agent.prompts import AGENT_SYSTEM_PROMPT, build_agent_user_prompt
from app.llm.agent.schemas import AgentReply
from app.llm.agent.techniques import TechniqueState, build_technique_block
from app.llm.errors import LLMConfigurationError, LLMResponseError, LLMTransportError
from app.llm.pool import pool

logger = logging.getLogger("gpt-support-llm.agent")

MAX_TOOL_HOPS = 3

_TEMPERATURE = 0.3
_MAX_TOKENS = 900
_MAX_ATTEMPTS = 2


@dataclass(slots=True)
class AgentRun:
    """Результат одного хода одноагентной ветки."""

    reply: AgentReply | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    llm_calls: int = 0
    repair_attempts: int = 0
    attempts: int = 0
    account_id: str = ""
    prefix_fp: str | None = None
    hops: int = 0
    error: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.reply is not None


def build_layers(
    *,
    user_message: str,
    profile_block: str = "",
    history: list[dict[str, str]] | None = None,
    rag_fragments: list[str] | None = None,
    patient_gender: str | None = None,
    last_bot_reply: str | None = None,
    session_goal: str | None = None,
    anchor_goal: str | None = None,
    technique_state: TechniqueState | None = None,
    technique_context: str = "",
    l0_note: str = "",
) -> prompt_assembly.PromptLayers:
    """Слои промпта агента — та же дисциплина, что и в старой ветке (шаг 2)."""
    technique_block = build_technique_block(
        user_message=user_message,
        context=technique_context or str(session_goal or ""),
        state=technique_state,
    )
    volatile = build_agent_user_prompt(
        user_message=user_message,
        rag_fragments=list(rag_fragments or []),
        patient_gender=patient_gender,
        last_bot_reply=last_bot_reply,
        session_goal=session_goal,
        technique_block=technique_block,
        l0_note=l0_note,
    )
    return prompt_assembly.PromptLayers(
        system=AGENT_SYSTEM_PROMPT,
        profile=profile_block,
        summary=prompt_assembly.build_summary_layer(anchor_goal=anchor_goal),
        window=prompt_assembly.window_from_history(
            history, exclude_last_user_message=user_message
        ),
        volatile=[prompt_assembly.Turn(role="user", content=volatile)],
    )


class Agent:
    """Одноагентная ветка поверх существующего ``AccountPool``."""

    def __init__(
        self,
        *,
        model_tier: str = "pro",
        strict_model_tier: bool = False,
        temperature: float = _TEMPERATURE,
        max_tokens: int = _MAX_TOKENS,
    ) -> None:
        self.model_tier = model_tier
        self.strict_model_tier = strict_model_tier
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def run(
        self,
        layers: prompt_assembly.PromptLayers,
        *,
        patient_id: int | None = None,
        thread_key: str = "",
        allowed_tools: list[str] | None = None,
        max_hops: int = MAX_TOOL_HOPS,
    ) -> AgentRun:
        started = time.monotonic()
        prefix_fp = layers.prefix_fingerprint()
        # Отпечаток в ключе кэша: стабильная часть сменилась — честный новый старт.
        cache_key = prompt_assembly.with_fingerprint(thread_key, prefix_fp) or None
        messages = layers.tail_messages()

        if allowed_tools:
            # Шаг 7. Пока инструменты не подключены, фаза сбора данных пропускается.
            logger.debug("[agent] tools requested but not wired yet: %s", allowed_tools)

        run = AgentRun(prefix_fp=prefix_fp)

        try:
            client = await pool.get_available(
                self.model_tier,
                allow_fallback=not self.strict_model_tier,
                sticky_key=thread_key or None,
            )
        except LLMConfigurationError:
            raise
        run.account_id = client.account_id

        last_error: str | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            run.attempts = attempt
            try:
                result = await client.structured(
                    messages,
                    layers.system,
                    AgentReply,
                    temperature=self.temperature,
                    step="agent",
                    patient_id=patient_id,
                    session_id=cache_key,
                    prefix_fp=prefix_fp,
                    max_tokens=self.max_tokens,
                )
            except (LLMResponseError, LLMTransportError) as exc:
                last_error = str(exc)
                run.llm_calls += 2  # основной вызов + починка внутри structured()
                run.repair_attempts += 1
                logger.warning("[agent] attempt %d failed: %s", attempt, exc)
                continue

            run.reply = result.parsed
            run.tokens_in += result.tokens_in
            run.tokens_out += result.tokens_out
            run.repair_attempts += result.repair_attempts
            run.llm_calls += 1 + result.repair_attempts
            run.latency_ms = int((time.monotonic() - started) * 1000)
            run.diagnostics = {
                "attempts_total": attempt,
                "llm_calls": run.llm_calls,
                "repair_attempts": run.repair_attempts,
                "prefix_fp": prefix_fp,
                "account_id": run.account_id,
                "model_tier": self.model_tier,
                "intent": result.parsed.intent,
                "safety_level": result.parsed.safety_level,
            }
            return run

        run.error = last_error or "agent failed without a classified error"
        run.latency_ms = int((time.monotonic() - started) * 1000)
        run.diagnostics = {
            "attempts_total": run.attempts,
            "llm_calls": run.llm_calls,
            "repair_attempts": run.repair_attempts,
            "prefix_fp": prefix_fp,
            "account_id": run.account_id,
            "model_tier": self.model_tier,
            "error": run.error,
        }
        return run
