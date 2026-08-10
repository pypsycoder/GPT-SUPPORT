"""
Бюджет токенов и оркестрация одного хода.

Здесь собирается всё вместе: роутер -> сборка промпта -> агент -> память.
Плюс политика компакции: когда сворачивать историю и что выкидывать первым.

Философия бюджета
-----------------
Не «сколько влезет в контекст», а «сколько мы готовы платить за этот ход».
Контекст GigaChat-2-Pro большой, и именно поэтому промпт незаметно распухает:
ошибки переполнения нет, есть только счёт в конце месяца.

Поэтому бюджет задаётся явно и в токенах, а не «на глазок по символам».
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_loop import Agent, AgentRun, summarize
from gigachat_client import GigaChatClient
from memory import FactCandidate, MemoryGate, MemoryStore, render_facts
from prompt_assembly import PromptLayers, Turn, approx_tokens, trim_window
from router import CascadeRouter, Intent

logger = logging.getLogger("giga.budget")


@dataclass(frozen=True, slots=True)
class Budget:
    """
    Потолки на слои промпта, в токенах.

    Значения — стартовая точка для чат-поддержки, а не истина.
    Калибруйте по своим логам: смотрите на p95 фактического расхода
    по каждому слою и режьте самый жирный.
    """
    system: int = 400
    profile: int = 250
    summary: int = 350
    window: int = 1200
    retrieval: int = 600
    output: int = 700

    @property
    def input_total(self) -> int:
        return self.system + self.profile + self.summary + self.window + self.retrieval


BUDGET_BY_INTENT: dict[Intent, Budget] = {
    # Болтовня не нуждается ни в профиле, ни в RAG.
    Intent.SMALLTALK: Budget(profile=0, summary=100, window=300, retrieval=0, output=150),
    # Эмоциональная поддержка: важна история, не важны факты из базы знаний.
    Intent.EMOTIONAL: Budget(retrieval=0, window=1600, output=600),
    Intent.SELFCARE:  Budget(),
    Intent.CLINICAL:  Budget(retrieval=400, output=600),
    # Обучение: наоборот, RAG важнее истории.
    Intent.EDUCATION: Budget(summary=200, window=600, retrieval=1200, output=800),
    Intent.LOGISTICS: Budget(profile=100, summary=100, window=400, retrieval=0, output=250),
    # Кризис — единственное место, где экономить нельзя.
    Intent.SAFETY:    Budget(profile=400, summary=600, window=2000, retrieval=400, output=900),
    Intent.OFFTOPIC:  Budget(profile=0, summary=0, window=200, retrieval=0, output=120),
}


# --------------------------------------------------------------------------- #
# Политика компакции
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class CompactionPolicy:
    """
    Когда сворачивать историю.

    Два триггера, оба нужны:
      * по объёму — защищает от длинных монологов;
      * по числу ходов — защищает от «тысячи коротких реплик».

    Свёртка запускается ПОСЛЕ ответа пациенту, в фоне. Пациент не ждёт.
    """
    max_window_tokens: int = 1200
    max_window_turns: int = 12
    # Сколько ходов оставить после свёртки. Оставлять 2 — плохо:
    # модель теряет нить. 4-6 — рабочий компромисс.
    keep_turns_after: int = 6

    def should_compact(self, turns: list[Turn]) -> bool:
        if len(turns) > self.max_window_turns:
            return True
        return sum(approx_tokens(t.content) for t in turns) > self.max_window_tokens


# --------------------------------------------------------------------------- #
# Оркестратор хода
# --------------------------------------------------------------------------- #

class TurnOrchestrator:
    """
    Один вход: обработать реплику пациента.
    Никаких «режимов оркестрации» и переключателей — путь всегда один,
    меняются только бюджет и набор инструментов.
    """

    def __init__(
        self,
        client: GigaChatClient,
        router: CascadeRouter,
        agent: Agent,
        store: MemoryStore,
        gate: MemoryGate,
        system_prompt: str,
        *,
        policy: CompactionPolicy | None = None,
    ) -> None:
        self.client = client
        self.router = router
        self.agent = agent
        self.store = store
        self.gate = gate
        self.system_prompt = system_prompt
        self.policy = policy or CompactionPolicy()

    async def handle(
        self,
        *,
        patient_id: int,
        thread_id: str,
        user_text: str,
        source: str = "text",
        retrieval_block: str = "",
        tool_context: dict[str, Any] | None = None,
    ) -> AgentRun:
        # 1. Маршрут -------------------------------------------------------
        route = await self.router.route(user_text, source=source)
        budget = BUDGET_BY_INTENT[route.intent]
        logger.info("route intent=%s level=%s conf=%.2f", route.intent, route.level, route.confidence)

        # 2. Память --------------------------------------------------------
        facts = await self.store.read_facts(patient_id) if budget.profile else []
        summary_text, _ = await self.store.latest_summary(thread_id) if budget.summary else ("", 0)
        window = await self.store.read_window(thread_id, limit=self.policy.max_window_turns)

        turns = [Turn(role=t["role"], content=t["content"]) for t in window.turns]
        kept, _evicted = trim_window(
            turns,
            max_turns=self.policy.max_window_turns,
            max_chars=budget.window * 4,
        )

        # 3. Сборка промпта ------------------------------------------------
        volatile: list[Turn] = []
        if retrieval_block and budget.retrieval:
            volatile.append(Turn(
                role="user",
                content=f"<справочные_материалы>\n{retrieval_block}\n</справочные_материалы>",
            ))
            volatile.append(Turn(role="assistant", content="Материалы приняты."))
        volatile.append(Turn(role="user", content=user_text))

        layers = PromptLayers(
            system=self.system_prompt,
            profile=render_facts(facts) if budget.profile else "",
            summary=summary_text[: budget.summary * 4] if budget.summary else "",
            window=kept,
            volatile=volatile,
        )

        # 4. Агент ---------------------------------------------------------
        self.agent.model = route.model
        self.agent.max_tokens = budget.output
        run = await self.agent.run(
            layers,
            patient_id=patient_id,
            thread_id=thread_id,
            allowed_tools=route.tools,
            tool_context={"patient_id": patient_id, **(tool_context or {})},
        )

        # 5. Запись хода ---------------------------------------------------
        await self.store.append_turn(thread_id, "user", user_text,
                                     tokens=approx_tokens(user_text))
        if run.reply is not None:
            await self.store.append_turn(thread_id, "assistant", run.reply.reply,
                                         tokens=approx_tokens(run.reply.reply))
            # 6. Кандидаты в память -> gate (не агент!) --------------------
            cands: list[FactCandidate] = []
            for raw in run.reply.memory_candidates:
                try:
                    cands.append(FactCandidate.model_validate(raw))
                except Exception:  # noqa: BLE001 — кривой кандидат просто отбрасывается
                    continue
            if cands:
                decisions = await self.gate.apply(patient_id, cands)
                logger.info("memory decisions: %s", [d.model_dump() for d in decisions])

        return run

    # --------------------------- фоновая свёртка --------------------------

    async def compact_if_needed(self, thread_id: str) -> bool:
        """Вызывать после ответа, вне критического пути (BackgroundTasks/воркер)."""
        window = await self.store.read_window(thread_id, limit=100)
        turns = [Turn(role=t["role"], content=t["content"]) for t in window.turns]
        if not self.policy.should_compact(turns):
            return False

        keep = self.policy.keep_turns_after
        evicted_rows = window.turns[:-keep] if len(window.turns) > keep else []
        if not evicted_rows:
            return False

        evicted = [Turn(role=r["role"], content=r["content"]) for r in evicted_rows]
        prev, _ = await self.store.latest_summary(thread_id)
        summary = await summarize(self.client, prev, evicted)

        seq_from = evicted_rows[0]["seq"]
        seq_to = evicted_rows[-1]["seq"]
        await self.store.save_summary(thread_id, summary.text, seq_from, seq_to)
        await self.store.mark_compacted(thread_id, seq_to)
        logger.info("compacted thread=%s seq %d..%d", thread_id, seq_from, seq_to)
        return True


# --------------------------------------------------------------------------- #
# Учёт
# --------------------------------------------------------------------------- #

async def log_run(db: Any, run: AgentRun, *, thread_id: str, patient_id: int,
                  step: str, session_key: str, prefix_fp: str) -> None:
    """
    Пишите КАЖДЫЙ вызов. Без этой таблицы разговор об оптимизации
    превращается в гадание: непонятно, где именно утекают токены.
    """
    for comp in run.calls:
        await db.execute(
            """
            INSERT INTO agent.call_log
                (thread_id, patient_id, step, model, session_key, prefix_fp,
                 prompt_tokens, completion_tokens, precached_tokens, total_tokens,
                 latency_ms, finish_reason, ok, error)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            """,
            thread_id, patient_id, step, comp.model, session_key, prefix_fp,
            comp.usage.prompt_tokens, comp.usage.completion_tokens,
            comp.usage.precached_prompt_tokens, comp.usage.total_tokens,
            comp.latency_ms, comp.finish_reason, run.error is None, run.error,
        )
