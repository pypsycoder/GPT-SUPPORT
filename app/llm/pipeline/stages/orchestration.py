"""
Compatibility orchestration stage.
"""

from __future__ import annotations

import time

from app.llm.pipeline.types import PipelineContext, PipelineStage


class OrchestrationStage(PipelineStage):
    @property
    def stage_name(self) -> str:
        return "orchestration"

    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()

        if context.should_skip_orchestration or context.supervisor_turn is not None:
            context.diagnostics["orchestration"] = {
                "enabled": False,
                "skipped": True,
                "reason": "supervisor_turn",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            return context

        context.diagnostics["orchestration"] = {
            "enabled": False,
            "skipped": True,
            "reason": "legacy_stage_unavailable",
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
        return context
