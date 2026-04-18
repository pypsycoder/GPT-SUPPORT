"""Supervisor Stage powered by Graph v2: intake -> delegation -> emotional expert."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.llm.errors import LLMResponseError
from app.llm.langgraph_supervisor import ExecutionKind, FirstModuleInput, run_first_module
from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.router import RequestType
from app.llm.supervisor import CurrentState, PendingQuestion, SupervisorTurnResult

logger = logging.getLogger("gpt-support-llm.pipeline.supervisor")

_META_MESSAGES = {"спасибо", "спс", "благодарю", "понятно", "угу", "ок", "хорошо"}


def _derive_message_type(user_message: str) -> str:
    normalized = str(user_message or "").strip().lower()
    if normalized in _META_MESSAGES:
        return "meta_message"
    return "full_message"


def _changed_state(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed[key] = after.get(key)
    return changed


def _merge_intake_context(previous: str | None, current: str | None, *, preserve_history: bool) -> str | None:
    previous_text = str(previous or "").strip()
    current_text = str(current or "").strip()
    if not current_text:
        return previous_text or None
    if not preserve_history or not previous_text or previous_text == current_text:
        return current_text
    if current_text in previous_text:
        return previous_text
    if previous_text in current_text:
        return current_text
    return f"{previous_text}. {current_text}"


def _build_updated_state(current_state: CurrentState, graph_state) -> CurrentState:
    updated = CurrentState.from_dict(current_state.to_dict())
    intake_card = graph_state.intake_card

    if intake_card is not None:
        if intake_card.problem and intake_card.problem != "не обозначена":
            updated.goal = intake_card.problem

        merged_context = _merge_intake_context(
            current_state.slots.get("intake_context"),
            intake_card.context,
            preserve_history=bool(current_state.pending_question or current_state.clarification_streak),
        )
        if merged_context:
            updated.slots["intake_context"] = merged_context

    if graph_state.execution_kind is ExecutionKind.ASK:
        previous_attempts = updated.pending_question.attempts if updated.pending_question else 0
        updated.pending_question = PendingQuestion(
            slot_name="clarify",
            question_text=graph_state.user_question or "",
            expected_kind="free_text",
            attempts=previous_attempts + 1,
            reason="intake",
        )
        updated.needs_clarification = True
        updated.clarification_streak = int(updated.clarification_streak or 0) + 1
        updated.last_selected_agents = []
    elif graph_state.execution_kind is ExecutionKind.DELEGATE:
        updated.pending_question = None
        updated.needs_clarification = bool(graph_state.needs_clarification)
        updated.clarification_streak = 0
        updated.last_selected_agents = list(graph_state.selected_agents)
    else:
        updated.pending_question = None
        updated.needs_clarification = False
        updated.clarification_streak = 0
        updated.last_selected_agents = []

    return updated


def _raise_if_failed(graph_state, supervisor_diagnostics: dict[str, Any]) -> None:
    intake_llm = ((graph_state.diagnostics.get("intake") or {}).get("llm") or {})
    if intake_llm.get("final_status") == "failed_after_retries":
        raise LLMResponseError(
            "supervisor intake analysis failed after 3 attempts",
            diagnostics={"supervisor": supervisor_diagnostics},
        )

    delegation_llm = ((graph_state.diagnostics.get("delegation") or {}).get("llm") or {})
    if graph_state.execution_kind is ExecutionKind.DELEGATE and delegation_llm.get("final_status") == "failed_after_retries":
        raise LLMResponseError(
            "supervisor delegation analysis failed after 3 attempts",
            diagnostics={"supervisor": supervisor_diagnostics},
        )

    expert_llm = ((graph_state.diagnostics.get("expert") or {}).get("llm") or {})
    if graph_state.execution_kind is ExecutionKind.DELEGATE and expert_llm.get("final_status") == "failed_after_retries":
        raise LLMResponseError(
            "supervisor emotional expert failed after 3 attempts",
            diagnostics={"supervisor": supervisor_diagnostics},
        )


class SupervisorStage(PipelineStage):
    @property
    def stage_name(self) -> str:
        return "supervisor"

    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()

        if context.classification is None:
            return context

        if context.classification.request_type is RequestType.SAFETY:
            context.diagnostics["supervisor"] = {
                "enabled": False,
                "reason": "safety_request",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            return context

        current_state = CurrentState.from_dict(context.supervisor_state)
        message_type = _derive_message_type(context.request.user_input)

        graph_state = await run_first_module(
            FirstModuleInput(
                user_message=context.request.user_input,
                current_state=current_state,
                message_type=message_type,
                model_tier=context.classification.model_tier.value,
                strict_model_tier=bool(context.request.strict_model_tier),
            )
        )

        updated_state = _build_updated_state(current_state, graph_state)
        before_state = current_state.to_dict()
        after_state = updated_state.to_dict()
        state_delta = _changed_state(before_state, after_state)

        supervisor_diagnostics = {
            "enabled": True,
            "message_type": message_type,
            "graph_path": list(graph_state.diagnostics.get("graph_path") or []),
            "intake": dict(graph_state.diagnostics.get("intake") or {}),
            "delegation": dict(graph_state.diagnostics.get("delegation") or {}),
            "expert": dict(graph_state.diagnostics.get("expert") or {}),
            "selected_agents": list(graph_state.selected_agents),
            "needs_clarification": bool(graph_state.needs_clarification),
            "execution_kind": graph_state.execution_kind.value if graph_state.execution_kind else None,
            "state_delta": state_delta,
            "state_after": after_state,
            "llm_totals": {
                "tokens_input": graph_state.total_tokens_input,
                "tokens_output": graph_state.total_tokens_output,
                "latency_ms": graph_state.total_latency_ms,
                "account_ids": list(graph_state.account_ids),
                "actual_model_tiers": list(graph_state.actual_model_tiers),
            },
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

        _raise_if_failed(graph_state, supervisor_diagnostics)

        reply = str(graph_state.final_reply or "").strip()
        if not reply:
            raise LLMResponseError(
                "supervisor graph v2 returned empty reply",
                diagnostics={"supervisor": supervisor_diagnostics},
            )

        turn = SupervisorTurnResult(
            reply=reply,
            state_delta=state_delta,
            updated_state=updated_state,
            message_type=message_type,
            selected_agents=list(graph_state.selected_agents),
            used_pending_answer=False,
            needs_clarification=bool(graph_state.needs_clarification),
            diagnostics=supervisor_diagnostics,
        )

        context.supervisor_turn = turn
        context.supervisor_state = after_state
        context.response_draft = reply
        context.response_tokens_input = int(graph_state.total_tokens_input or 0)
        context.response_tokens_output = int(graph_state.total_tokens_output or 0)
        context.response_account_id = graph_state.account_ids[-1] if graph_state.account_ids else "SUPERVISOR"
        context.response_actual_model_tier = (
            graph_state.actual_model_tiers[-1] if graph_state.actual_model_tiers else context.classification.model_tier.value
        )
        context.diagnostics["supervisor"] = supervisor_diagnostics

        logger.info(
            "[supervisor] patient=%d execution=%s selected_agents=%s",
            context.request.patient_id,
            supervisor_diagnostics.get("execution_kind") or "-",
            ",".join(graph_state.selected_agents) or "-",
        )
        return context
