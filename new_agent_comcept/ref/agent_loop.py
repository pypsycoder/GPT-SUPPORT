"""
Агентный цикл: один агент + инструменты + структурный вывод.

Заменяет цепочку router -> specialists -> composer -> critic -> rewrite
(5-7 вызовов) на 1-3 вызова, из которых 2-й и 3-й почти целиком попадают в кэш.

Инвариант цикла (нарушение = ошибка 422 от GigaChat):
    если ассистент вернул function_call, в историю ОБЯЗАНЫ уйти оба сообщения:
        {"role": "assistant", "content": "", "function_call": {...},
         "functions_state_id": "..."}
        {"role": "function",  "content": "<json-результат>"}
    Иначе: «every assistant function call must have a result in history».

Второй инвариант — про деньги:
    session_id один на весь цикл и на весь тред. Тогда 2-й вызов после
    инструмента почти весь префикс берёт из кэша.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from pydantic import BaseModel, Field

from gigachat_client import Completion, GigaChatClient, Usage
from prompt_assembly import PromptLayers, Turn, session_key
from tools import ToolRegistry

logger = logging.getLogger("giga.agent")

MAX_TOOL_HOPS = 3   # выше — почти всегда зацикливание, а не польза


# --------------------------------------------------------------------------- #
# Контракт финального ответа
# --------------------------------------------------------------------------- #

class SafetyFlag(BaseModel):
    level: str = Field(description="none | concern | urgent")
    reason: str = ""


class AgentReply(BaseModel):
    """
    Структурный вывод вместо свободного текста.

    Зачем схема, если нужен просто текст: вместе с текстом мы бесплатно
    (в одном вызове) получаем маршрутные поля — safety, CTA, кандидатов
    в память. Раньше на это уходили отдельные вызовы critic и memory-writer.
    """

    reply: str = Field(max_length=1500, description="Текст пациенту. Русский, без markdown-разметки.")
    safety: SafetyFlag
    # Кандидаты в долгосрочную память. Решение о записи принимает MemoryGate.
    memory_candidates: list[dict[str, Any]] = Field(default_factory=list, max_length=3)
    # Предложение следующего шага: урок, практика, запись показателей
    next_action: str | None = Field(default=None, max_length=80)


@dataclass(slots=True)
class AgentRun:
    reply: AgentReply | None
    usage: Usage
    hops: int
    latency_ms: int
    calls: list[Completion] = field(default_factory=list)
    error: str | None = None

    @property
    def cache_hit_ratio(self) -> float:
        return self.usage.cache_hit_ratio


# --------------------------------------------------------------------------- #
# Цикл
# --------------------------------------------------------------------------- #

class Agent:
    def __init__(
        self,
        client: GigaChatClient,
        registry: ToolRegistry,
        *,
        model: str = "GigaChat-2-Pro",
        max_tokens: int = 700,
        temperature: float = 0.3,
    ) -> None:
        self.client = client
        self.registry = registry
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def run(
        self,
        layers: PromptLayers,
        *,
        patient_id: int,
        thread_id: str,
        allowed_tools: list[str] | None,
        tool_context: dict[str, Any],
        max_hops: int = MAX_TOOL_HOPS,
    ) -> AgentRun:
        started = time.monotonic()
        sid = session_key(patient_id, thread_id, layers.prefix_fingerprint())
        messages = layers.build()
        specs = self.registry.specs(allowed_tools) if allowed_tools else None

        total = Usage()
        calls: list[Completion] = []

        # ---- Фаза 1: сбор данных инструментами -------------------------------
        for hop in range(max_hops):
            comp = await self.client.chat(
                messages,
                model=self.model,
                session_id=sid,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                functions=specs,
                function_call="auto" if specs else "none",
            )
            calls.append(comp)
            total = total + comp.usage

            if comp.blocked:
                return AgentRun(
                    reply=None, usage=total, hops=hop,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    calls=calls, error="blacklist",
                )

            if comp.function_call is None:
                # Модель готова отвечать. Переходим к структурному финалу.
                break

            fc = comp.function_call
            logger.info("tool call hop=%d name=%s", hop, fc.name)

            result = await self.registry.invoke(fc.name, fc.arguments, **tool_context)

            # Оба сообщения обязательны и именно в таком порядке.
            messages.append({
                "role": "assistant",
                "content": "",
                "function_call": {"name": fc.name, "arguments": fc.arguments},
                **({"functions_state_id": comp.functions_state_id}
                   if comp.functions_state_id else {}),
            })
            messages.append({"role": "function", "content": result})
        else:
            logger.warning("tool loop exhausted after %d hops", max_hops)

        # ---- Фаза 2: финальный структурный ответ -----------------------------
        # Отдельным вызовом, потому что смешивать functions и response_format
        # в одном запросе — способ получить непредсказуемое поведение.
        # Вызов дешёвый: весь префикс уже в кэше.
        messages.append({
            "role": "user",
            "content": "Сформируй итоговый ответ пациенту строго по схеме.",
        })
        try:
            reply, comp = await self.client.structured(
                messages, AgentReply,
                model=self.model, session_id=sid,
                temperature=self.temperature, max_tokens=self.max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            return AgentRun(
                reply=None, usage=total, hops=len(calls),
                latency_ms=int((time.monotonic() - started) * 1000),
                calls=calls, error=f"structured_failed:{exc}",
            )

        calls.append(comp)
        total = total + comp.usage
        return AgentRun(
            reply=reply, usage=total, hops=len(calls) - 1,
            latency_ms=int((time.monotonic() - started) * 1000),
            calls=calls,
        )


# --------------------------------------------------------------------------- #
# Свёртка истории (эпизодическая память)
# --------------------------------------------------------------------------- #

SUMMARIZER_SYSTEM = (
    "Ты сжимаешь диалог поддержки пациента на гемодиализе. "
    "Сохраняй: заявленную проблему, договорённости, что уже пробовали, "
    "предпочтения по формату помощи, незакрытые вопросы. "
    "Убирай: приветствия, вежливые формулы, повторы, эмоциональные усилители. "
    "Не добавляй ничего, чего не было в диалоге. "
    "Не давай медицинских оценок и рекомендаций."
)


class Summary(BaseModel):
    text: str = Field(max_length=900, description="Сжатый итог, 4-8 предложений")
    open_questions: list[str] = Field(default_factory=list, max_length=3)


async def summarize(
    client: GigaChatClient,
    previous_summary: str,
    evicted: Sequence[Turn],
    *,
    model: str = "GigaChat-2",   # Lite: свёртка — простая задача, Pro тут не нужен
) -> Summary:
    """
    Rolling summary: старая свёртка + вытесненные ходы -> новая свёртка.

    Вызывается НЕ на каждом ходу, а по триггеру (см. budget.py).
    Считайте её фоновой задачей: пациент не должен ждать свёртку.

    session_id намеренно не передаётся: это разовая операция с уникальным
    входом, кэш ей не поможет, а общий session_id она бы только испортила.
    """
    dialog = "\n".join(f"{t.role}: {t.content}" for t in evicted)
    user = (
        (f"<предыдущий_итог>\n{previous_summary}\n</предыдущий_итог>\n\n" if previous_summary else "")
        + f"<новые_реплики>\n{dialog}\n</новые_реплики>"
    )
    summary, _ = await client.structured(
        [{"role": "system", "content": SUMMARIZER_SYSTEM}, {"role": "user", "content": user}],
        Summary,
        model=model,
        temperature=0.1,
        max_tokens=400,
    )
    return summary


def dumps_compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
