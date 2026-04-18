"""
Compatibility validation stage.
"""

from __future__ import annotations

import time

from app.llm.pipeline.types import PipelineContext, PipelineStage


class ValidationStage(PipelineStage):
    @property
    def stage_name(self) -> str:
        return "validation"

    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()

        if context.response_draft:
            context.diagnostics["validation"] = {
                "triggered": True,
                "status": "supervisor_draft_kept",
                "reasons": ["no_action_step"],
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            return context

        context.diagnostics["validation"] = {
            "triggered": False,
            "skipped": True,
            "reason": "no_response_draft",
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
        return context
