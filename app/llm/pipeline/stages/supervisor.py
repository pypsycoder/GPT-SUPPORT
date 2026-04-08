"""
Supervisor Stage - stateful MVP orchestrator.

Runs after Classification and becomes the main decision-making path for
ordinary text requests while keeping pipeline compatibility intact.
"""

from __future__ import annotations

import logging
import time

from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.router import RequestType
from app.llm.supervisor import CurrentState, SupervisorOrchestrator

logger = logging.getLogger("gpt-support-llm.pipeline.supervisor")


class SupervisorStage(PipelineStage):
    """Stage 1.5: main stateful supervisor turn."""

    @property
    def stage_name(self) -> str:
        return "supervisor"

    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()

        if context.classification.request_type in {RequestType.SAFETY, RequestType.QUICK_ACTION}:
            context.diagnostics["supervisor"] = {
                "enabled": False,
                "reason": "legacy_path",
                "latency_ms": 0,
            }
            return context

        orchestrator = SupervisorOrchestrator()
        turn = orchestrator.handle_message(
            user_message=context.request.user_input,
            current_state=CurrentState.from_dict(context.supervisor_state),
        )

        context.supervisor_turn = turn
        context.supervisor_state = turn.updated_state.to_dict()
        context.response_draft = turn.reply
        context.should_skip_orchestration = True
        context.diagnostics["supervisor"] = {
            "enabled": True,
            "message_type": turn.message_type,
            "selected_agents": list(turn.selected_agents),
            "used_pending_answer": turn.used_pending_answer,
            "needs_clarification": turn.needs_clarification,
            "state_delta": dict(turn.state_delta),
            "turn_diagnostics": dict(turn.diagnostics),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

        logger.info(
            "[supervisor] patient=%d message_type=%s agents=%s clarify=%s",
            context.request.patient_id,
            turn.message_type,
            ",".join(turn.selected_agents) or "-",
            turn.needs_clarification,
        )

        return context
