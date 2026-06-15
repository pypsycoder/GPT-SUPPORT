"""Supervisor Stage powered by Graph v2: intake -> delegation -> emotional expert."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from app.llm.context_builder_optimized import build_context_bundle_optimized
from app.llm.errors import LLMResponseError
from app.llm.langgraph_supervisor import ExecutionKind, FirstModuleInput, run_first_module
from app.llm.langgraph_supervisor.models import EmotionalExpertCard, ExpertStrategy
from app.llm.technique_library import get_technique_by_id
from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.supervisor import CurrentState, PendingQuestion, SupervisorTurnResult
from app.llm.supervisor.classification import detect_message_type

logger = logging.getLogger("gpt-support-llm.pipeline.supervisor")


def _derive_message_type(user_message: str, current_state: CurrentState) -> str:
    return detect_message_type(user_message, current_state)


def _changed_state(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changed[key] = after.get(key)
    return changed


_CONTEXT_PLACEHOLDER = "контекст пока не раскрыт"

_UNKNOWN_REASON_PHRASES = (
    "причина тревоги неизвестна",
    "причина пользователю не известна",
    "причина не известна",
    "причина неизвестна",
)


def _has_unknown_reason(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _UNKNOWN_REASON_PHRASES)


def _strip_unknown_reason_sentences(text: str) -> str:
    parts = [p.strip() for p in text.split(".") if p.strip()]
    parts = [p for p in parts if not _has_unknown_reason(p)]
    return ". ".join(parts)


def _normalize_for_compare(text: str) -> str:
    """Collapse consecutive dots and whitespace for substring comparison."""
    result = text
    while ".." in result:
        result = result.replace("..", ".")
    return " ".join(result.split()).strip()


def _strip_placeholder(text: str) -> str:
    """Remove leading placeholder sentences from accumulated context."""
    parts = [p.strip() for p in text.split(".") if p.strip()]
    parts = [p for p in parts if p.lower() != _CONTEXT_PLACEHOLDER]
    return ". ".join(parts)


def _merge_intake_context(previous: str | None, current: str | None, *, preserve_history: bool) -> str | None:
    previous_text = str(previous or "").strip()
    current_text = str(current or "").strip()
    if not current_text or current_text.lower() == _CONTEXT_PLACEHOLDER:
        return previous_text or None
    # Replace placeholder-only previous with real context
    if previous_text.lower() == _CONTEXT_PLACEHOLDER:
        previous_text = ""
    if not preserve_history or not previous_text or previous_text == current_text:
        return current_text
    # Strip any stale placeholder from accumulated text before merging
    previous_clean = _strip_placeholder(previous_text)
    # Strip "unknown reason" stubs if new context provides a concrete cause
    if not _has_unknown_reason(current_text):
        previous_clean = _strip_unknown_reason_sentences(previous_clean)
    if not previous_clean or previous_clean == current_text:
        return current_text
    # Normalize before substring checks to handle "..." vs "." inconsistencies
    previous_norm = _normalize_for_compare(previous_clean)
    current_norm = _normalize_for_compare(current_text)
    if current_norm in previous_norm:
        return previous_clean
    if previous_norm in current_norm:
        return current_text
    return f"{previous_clean}. {current_text}"


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
        expert_card = getattr(graph_state, "expert_card", None)
        follow_up = str(getattr(expert_card, "follow_up", "") or "").strip()
        if bool(graph_state.needs_clarification) and follow_up and follow_up.lower() != "нет":
            previous_attempts = (
                updated.pending_question.attempts
                if updated.pending_question and updated.pending_question.reason == "expert"
                else 0
            )
            updated.pending_question = PendingQuestion(
                slot_name="expert_follow_up",
                question_text=follow_up,
                expected_kind="free_text",
                attempts=previous_attempts + 1,
                reason="expert",
            )
            updated.needs_clarification = True
        else:
            updated.pending_question = None
            updated.needs_clarification = False
        updated.clarification_streak = 0
        updated.last_selected_agents = list(graph_state.selected_agents)
    else:
        updated.pending_question = None
        updated.needs_clarification = False
        updated.clarification_streak = 0
        updated.last_selected_agents = []

    final_reply = getattr(graph_state, "final_reply", None)
    if final_reply:
        updated.last_bot_reply = str(final_reply).strip() or None

    expert_card = getattr(graph_state, "expert_card", None)
    if isinstance(expert_card, EmotionalExpertCard):
        updated.last_expert_effectiveness = expert_card.effectiveness.value
        updated.last_expert_strategy = expert_card.strategy.value
        step = str(expert_card.step_now or "").strip()
        match = re.match(r'^\[(p\d+)\]', step)
        new_technique_id = match.group(1) if match else None
        step_text = step[match.end():].strip() if match else None
        # Defensive: if we're mid-interactive-flow and expert omitted [pNN] prefix,
        # auto-attribute the step to the current technique so step index advances.
        _step_is_action = step and step.lower() not in ("нет", "no", "")
        if new_technique_id is None and _step_is_action:
            _current_id = str(current_state.current_technique_id or "").strip()
            if _current_id:
                _card = get_technique_by_id(_current_id)
                if _card and _card.interactive:
                    new_technique_id = _current_id
                    step_text = step
        # Preserve current_technique_id during reflection/follow-up turns (step_now = нет).
        # Only clear it when explicitly closing or when a new technique is delivered.
        if new_technique_id is not None:
            updated.current_technique_id = new_technique_id
        elif expert_card.strategy is ExpertStrategy.CLOSE:
            updated.current_technique_id = None
        # else: продолжить/углубить with follow_up — keep current_technique_id from state copy
        updated.last_expert_step = step_text or None
        if new_technique_id:
            recent = list(updated.recent_technique_ids)
            if not recent or recent[-1] != new_technique_id:
                recent.append(new_technique_id)
            updated.recent_technique_ids = recent[-5:]
            if new_technique_id == current_state.current_technique_id:
                updated.current_technique_turns = int(current_state.current_technique_turns or 0) + 1
            else:
                updated.current_technique_turns = 1
            # Advance step index for interactive techniques
            card = get_technique_by_id(new_technique_id)
            if card and card.interactive:
                if new_technique_id != current_state.current_technique_id:
                    updated.current_step_index = 1  # just delivered step 0
                else:
                    prev = int(current_state.current_step_index or 0)
                    if prev >= len(card.steps):
                        # углубить after all steps done: treat as fresh restart
                        updated.current_step_index = 1
                    else:
                        updated.current_step_index = min(prev + 1, len(card.steps))
            else:
                updated.current_step_index = 0

    return updated


async def _load_education_grounding(context: PipelineContext) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    if context.request.db is None:
        return [], [], {"enabled": False, "reason": "db_unavailable"}

    try:
        bundle = await build_context_bundle_optimized(
            context.request.patient_id,
            context.request.db,
            context.request.user_input,
        )
    except Exception as exc:
        logger.warning("[supervisor] education grounding failed patient=%d: %s", context.request.patient_id, exc)
        return [], [], {"enabled": False, "reason": "grounding_error", "error": str(exc)}

    context_payload = dict(bundle.get("context") or {})
    rag_views = dict(context_payload.get("rag_views") or {})
    grounding_items = [
        dict(item) for item in (context_payload.get("rag_grounding_items") or []) if isinstance(item, dict)
    ]
    education_view = [str(item) for item in (rag_views.get("education") or []) if str(item).strip()]
    diagnostics = {
        "enabled": True,
        "view_count": len(education_view),
        "grounding_count": len(grounding_items),
        "rag": dict((bundle.get("diagnostics") or {}).get("rag") or {}),
    }
    return education_view, grounding_items, diagnostics


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
        selected_agents = list(graph_state.selected_agents or [])
        expert_name = "education expert" if selected_agents == ["education"] else "emotional expert"
        raise LLMResponseError(
            f"supervisor {expert_name} failed after 3 attempts",
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

        current_state = CurrentState.from_dict(context.supervisor_state)
        message_type = _derive_message_type(context.request.user_input, current_state)
        education_rag_context, education_rag_grounding_items, education_grounding_diagnostics = (
            await _load_education_grounding(context)
        )
        context.education_rag_context = education_rag_context
        context.education_rag_grounding_items = education_rag_grounding_items

        graph_state = await run_first_module(
            FirstModuleInput(
                user_message=context.request.user_input,
                current_state=current_state,
                message_type=message_type,
                model_tier=context.classification.model_tier.value,
                strict_model_tier=bool(context.request.strict_model_tier),
                education_rag_context=education_rag_context,
                education_rag_grounding_items=education_rag_grounding_items,
                patient_gender=context.request.patient_gender,
            )
        )

        updated_state = _build_updated_state(current_state, graph_state)
        before_state = current_state.to_dict()
        after_state = updated_state.to_dict()
        state_delta = _changed_state(before_state, after_state)

        supervisor_diagnostics = {
            "enabled": True,
            "request_type": context.classification.request_type.value,
            "message_type": message_type,
            "graph_path": list(graph_state.diagnostics.get("graph_path") or []),
            "intake": dict(graph_state.diagnostics.get("intake") or {}),
            "delegation": dict(graph_state.diagnostics.get("delegation") or {}),
            "expert": dict(graph_state.diagnostics.get("expert") or {}),
            "selected_agents": list(graph_state.selected_agents),
            "needs_clarification": bool(graph_state.needs_clarification),
            "execution_kind": graph_state.execution_kind.value if graph_state.execution_kind else None,
            "education_grounding": education_grounding_diagnostics,
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
