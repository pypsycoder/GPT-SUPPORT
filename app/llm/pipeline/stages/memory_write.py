"""
Memory write stage — шаг 5: gate записи в персистентную семантическую память.

Кандидаты приходят только из одноагентной ветки (``AgentReply.memory_candidates``,
см. ``app.llm.pipeline.stages.supervisor``): старая ветка ``langgraph_supervisor``
такого поля не отдаёт. Стадия только читает БД для дедупа и добавляет объекты
в сессию — коммит остаётся в роутере (``app/routers/chat.py``), как того
требует CLAUDE.md.
"""

from __future__ import annotations

import time

from app.llm import memory_store
from app.llm.pipeline.types import PipelineContext, PipelineStage


class MemoryWriteStage(PipelineStage):
    @property
    def stage_name(self) -> str:
        return "memory_write"

    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()

        memory_diag = dict(context.diagnostics.get("memory") or {})
        memory_diag.setdefault("reads", {})
        memory_diag.setdefault("candidates", [])
        memory_diag.setdefault("write_decisions", [])
        memory_diag.setdefault("proposed_st_entries", [])  # ST закрыта chat_supervisor_states, не пишем
        memory_diag.setdefault("proposed_lt_entries", [])

        candidates = list(
            (context.diagnostics.get("supervisor") or {}).get("agent", {}).get("memory_candidates") or []
        )

        if candidates and context.request.db is not None:
            memory_diag["candidates"] = candidates
            decisions = await memory_store.stage_candidates(
                context.request.db,
                patient_id=context.request.patient_id,
                candidates=candidates,
            )
            memory_diag["write_decisions"] = [
                {"text": d.text, "action": d.action, "fact_id": d.fact_id} for d in decisions
            ]
            memory_diag["proposed_lt_entries"] = [
                {"text": d.text, "action": d.action}
                for d in decisions
                if d.action in ("created_pending", "promoted", "refreshed")
            ]

        memory_diag["latency_ms"] = int((time.monotonic() - started) * 1000)
        context.diagnostics["memory"] = memory_diag
        return context
