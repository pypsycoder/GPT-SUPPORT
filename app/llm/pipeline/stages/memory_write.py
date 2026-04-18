"""
Compatibility memory write stage.
"""

from __future__ import annotations

import time

from app.llm.pipeline.types import PipelineContext, PipelineStage


class MemoryWriteStage(PipelineStage):
    @property
    def stage_name(self) -> str:
        return "memory_write"

    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()

        memory_diag = dict(context.diagnostics.get("memory") or {})
        memory_diag.setdefault("reads", context.memory_reads or {})
        memory_diag.setdefault("candidates", [])
        memory_diag.setdefault("write_decisions", [])
        memory_diag.setdefault("proposed_st_entries", [])
        memory_diag.setdefault("proposed_lt_entries", [])
        memory_diag["latency_ms"] = int((time.monotonic() - started) * 1000)
        context.diagnostics["memory"] = memory_diag
        return context
