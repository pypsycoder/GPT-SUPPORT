"""Graph v2 nodes for intake -> delegation -> emotional expert."""

from __future__ import annotations

import re

from app.llm.langgraph_supervisor.models import (
    BinaryChoice,
    DelegationCard,
    DelegationExpert,
    EducationExpertCard,
    EmotionalExpertCard,
    ExecutionKind,
    ExpertStrategy,
    FirstModuleState,
    IntakeCard,
    ValidationDecision,
)
from app.llm.langgraph_supervisor.policy import (
    build_education_reply,
    build_emotional_reply,
    build_finish_reply,
    build_intake_reply,
    extract_delegation_card,
    extract_education_expert_card,
    extract_emotional_expert_card,
    extract_intake_card,
    validate_delegation_card,
    validate_education_expert_card,
    validate_emotional_expert_card,
    validate_intake_card,
)
from app.llm.supervisor.short_answers import is_unknown_reason_answer
from app.llm.technique_library import get_technique_by_id

_MAX_CLARIFICATION_STREAK = 2
_UNDEFINED_PROBLEM = "не обозначена"
_NO_CONTEXT_VALUES = {"", "нет", "контекст пока не раскрыт"}
_UNKNOWN_REASON_CONTEXT = "причина пользователю не известна"


def _mark_node(state: FirstModuleState, node_name: str) -> None:
    graph_path = state.diagnostics.setdefault("graph_path", [])
    if not isinstance(graph_path, list):
        graph_path = []
        state.diagnostics["graph_path"] = graph_path
    graph_path.append(node_name)


def _normalize_question_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _merge_unknown_reason_context(*values: str | None) -> str:
    parts: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text.lower() in _NO_CONTEXT_VALUES:
            continue
        if text not in parts:
            parts.append(text)
    if _UNKNOWN_REASON_CONTEXT not in parts:
        parts.append(_UNKNOWN_REASON_CONTEXT)
    return ". ".join(parts)


def _should_route_to_emotional_expert(state: FirstModuleState) -> bool:
    """True если эмоциональный эксперт уже был активен и сессия не завершена."""
    if "emotional_support" not in state.current_state.last_selected_agents:
        return False
    if state.current_state.last_expert_strategy == ExpertStrategy.CLOSE.value:
        return False
    return True


def _delegation_targets(state: FirstModuleState, expert: DelegationExpert) -> bool:
    return (
        state.execution_kind is ExecutionKind.DELEGATE
        and state.delegation_validation is ValidationDecision.ACCEPT
        and state.delegation_card is not None
        and state.delegation_card.expert is expert
    )


def _merge_expert_follow_up_context(
    previous: str | None,
    answer: str | None,
    label: str | None = None,
) -> str:
    previous_text = str(previous or "").strip()
    answer_text = str(answer or "").strip()
    if not answer_text:
        return previous_text
    addition = f"{label}: {answer_text}" if label else f"ответ: {answer_text}"
    if not previous_text:
        return addition
    return f"{previous_text.rstrip('.')}. {addition}"


def _normalize_unknown_reason_intake_card(state: FirstModuleState, card: IntakeCard | None) -> tuple[IntakeCard | None, bool]:
    if card is None:
        return None, False

    pending = state.current_state.pending_question
    if pending is None or pending.reason != "intake":
        return card, False
    if not is_unknown_reason_answer(state.user_message):
        return card, False

    problem = str(card.problem or "").strip()
    if not problem or problem == _UNDEFINED_PROBLEM:
        problem = str(state.current_state.goal or "").strip()
    if not problem or problem == _UNDEFINED_PROBLEM:
        return card, False

    return (
        IntakeCard(
            problem=problem,
            context=_merge_unknown_reason_context(
                state.current_state.slots.get("intake_context"),
            ),
            needs_clarification=BinaryChoice.NO,
            question="нет",
            ready_to_delegate=BinaryChoice.YES,
            rationale="пользователь не может назвать причину, поэтому запрос передается эксперту без новых уточнений",
        ),
        True,
    )


def _restore_dropped_context(state: FirstModuleState, card: IntakeCard | None) -> tuple[IntakeCard | None, bool]:
    """Восстанавливает goal/context если intake LLM сбросил их при ответе на pending intake-вопрос."""
    if card is None:
        return None, False
    if str(card.problem or "").strip() != _UNDEFINED_PROBLEM:
        return card, False

    pending = state.current_state.pending_question
    if pending is None or pending.reason != "intake":
        return card, False

    existing_goal = str(state.current_state.goal or "").strip()
    if not existing_goal or existing_goal == _UNDEFINED_PROBLEM:
        return card, False

    existing_context = str(state.current_state.slots.get("intake_context") or "").strip()
    return (
        IntakeCard(
            problem=existing_goal,
            context=existing_context or card.context,
            needs_clarification=BinaryChoice.NO,
            question="нет",
            ready_to_delegate=BinaryChoice.YES,
            rationale="intake не должен сбрасывать накопленную проблему при ответе пользователя на уточняющий вопрос",
        ),
        True,
    )


def _build_context_label(state: FirstModuleState) -> str | None:
    """Build a context label describing what the patient's answer is responding to."""
    pending_q = state.current_state.pending_question
    if pending_q is not None:
        return f"на вопрос «{pending_q.question_text}»"
    tech_id = str(state.current_state.current_technique_id or "").strip()
    if not tech_id:
        return None
    step_text = str(state.current_state.last_expert_step or "").strip()
    if step_text:
        card = get_technique_by_id(tech_id)
        if card and card.interactive and card.steps:
            # current_step_index is next-to-deliver; just-delivered is index (step_idx+1 = current)
            step_num = int(state.current_state.current_step_index or 1)
            total = len(card.steps)
            short = step_text[:60].rstrip() + ("…" if len(step_text) > 60 else "")
            return f"[{tech_id}] шаг {step_num}/{total} «{short}»"
        short = step_text[:60].rstrip() + ("…" if len(step_text) > 60 else "")
        return f"[{tech_id}] шаг «{short}»"
    return f"[{tech_id}] ответ"


async def intake_analyze_node(state: FirstModuleState) -> FirstModuleState:
    _mark_node(state, "intake_analyze")
    if _should_route_to_emotional_expert(state):
        problem = str(state.current_state.goal or "").strip() or _UNDEFINED_PROBLEM
        context_label = _build_context_label(state)
        state.intake_card = IntakeCard(
            problem=problem,
            context=_merge_expert_follow_up_context(
                state.current_state.slots.get("intake_context"),
                state.user_message,
                label=context_label,
            ),
            needs_clarification=BinaryChoice.NO,
            question="нет",
            ready_to_delegate=BinaryChoice.YES,
            rationale="эмоциональная сессия активна и не завершена — запрос возвращается эксперту напрямую",
        )
        state.diagnostics["intake"] = {
            "card": state.intake_card.to_dict(),
            "llm": {"synthetic_expert_follow_up": True},
        }
        return state

    card, step_diagnostics = await extract_intake_card(state)
    card, normalized = _normalize_unknown_reason_intake_card(state, card)
    card, context_restored = _restore_dropped_context(state, card)
    diagnostics = dict(step_diagnostics or {})
    if normalized:
        diagnostics["normalized_unknown_reason"] = True
    if context_restored:
        diagnostics["context_restored"] = True
    state.intake_card = card
    state.diagnostics["intake"] = {
        "card": card.to_dict() if card else None,
        "llm": diagnostics,
    }
    return state


def intake_validate_node(state: FirstModuleState) -> FirstModuleState:
    _mark_node(state, "intake_validate")
    card = state.intake_card
    if card is None:
        state.intake_validation = ValidationDecision.RETRY
        state.intake_error = "intake_card is missing"
    else:
        try:
            validate_intake_card(card)
            state.intake_validation = ValidationDecision.ACCEPT
            state.intake_error = None
        except ValueError as exc:
            state.intake_validation = ValidationDecision.RETRY
            state.intake_error = str(exc)

    diagnostics = dict(state.diagnostics.get("intake") or {})
    diagnostics["validation"] = {
        "decision": state.intake_validation.value if state.intake_validation else None,
        "error": state.intake_error,
    }
    state.diagnostics["intake"] = diagnostics
    return state


def intake_execute_node(state: FirstModuleState) -> FirstModuleState:
    _mark_node(state, "intake_execute")
    if state.intake_validation is not ValidationDecision.ACCEPT or state.intake_card is None:
        state.execution_kind = ExecutionKind.FINISH
        state.final_reply = "Извини, я не смог корректно разобрать запрос."
        return state

    card = state.intake_card
    streak = state.current_state.clarification_streak
    previous_question = _normalize_question_text(
        getattr(state.current_state.pending_question, "question_text", None)
    )
    current_question = _normalize_question_text(card.question)
    state.needs_clarification = card.needs_clarification is BinaryChoice.YES

    if (
        card.needs_clarification is BinaryChoice.YES
        and streak >= _MAX_CLARIFICATION_STREAK
        and card.problem not in {"", _UNDEFINED_PROBLEM}
    ):
        state.execution_kind = ExecutionKind.DELEGATE
        state.needs_clarification = False
        return state

    if (
        card.needs_clarification is BinaryChoice.YES
        and streak >= 1
        and previous_question
        and current_question
        and previous_question == current_question
        and card.problem not in {"", _UNDEFINED_PROBLEM}
    ):
        state.execution_kind = ExecutionKind.DELEGATE
        state.needs_clarification = False
        return state

    if card.needs_clarification is BinaryChoice.YES:
        state.execution_kind = ExecutionKind.ASK
        state.user_question = card.question
        state.final_reply = build_intake_reply(
            card, is_first_turn=not bool(state.current_state.last_bot_reply)
        )
        return state

    if card.ready_to_delegate is BinaryChoice.YES:
        state.execution_kind = ExecutionKind.DELEGATE
        return state

    state.execution_kind = ExecutionKind.FINISH
    state.final_reply = build_finish_reply(state.user_message)
    return state


async def delegation_analyze_node(state: FirstModuleState) -> FirstModuleState:
    if state.execution_kind is not ExecutionKind.DELEGATE:
        return state
    _mark_node(state, "delegation_analyze")

    if _should_route_to_emotional_expert(state):
        state.delegation_card = DelegationCard(
            expert=DelegationExpert.EMOTIONAL_SUPPORT,
            task="продолжить эмоциональную поддержку — оценить реакцию пациента и выбрать следующий шаг",
            rationale="эмоциональная сессия активна, intake пропускается, запрос идёт напрямую к эксперту",
        )
        state.diagnostics["delegation"] = {
            "card": state.delegation_card.to_dict(),
            "llm": {"synthetic_expert_follow_up": True},
        }
        return state

    card, step_diagnostics = await extract_delegation_card(state)
    state.delegation_card = card
    state.diagnostics["delegation"] = {
        "card": card.to_dict() if card else None,
        "llm": step_diagnostics,
    }
    return state


def delegation_validate_node(state: FirstModuleState) -> FirstModuleState:
    if state.execution_kind is not ExecutionKind.DELEGATE:
        return state
    _mark_node(state, "delegation_validate")

    card = state.delegation_card
    if card is None:
        state.delegation_validation = ValidationDecision.RETRY
        state.delegation_error = "delegation_card is missing"
    else:
        try:
            validate_delegation_card(card)
            state.delegation_validation = ValidationDecision.ACCEPT
            state.delegation_error = None
        except ValueError as exc:
            state.delegation_validation = ValidationDecision.RETRY
            state.delegation_error = str(exc)

    diagnostics = dict(state.diagnostics.get("delegation") or {})
    diagnostics["validation"] = {
        "decision": state.delegation_validation.value if state.delegation_validation else None,
        "error": state.delegation_error,
    }
    state.diagnostics["delegation"] = diagnostics
    return state


async def invoke_emotional_expert_node(state: FirstModuleState) -> FirstModuleState:
    if state.execution_kind is not ExecutionKind.DELEGATE:
        return state
    if state.delegation_validation is not ValidationDecision.ACCEPT:
        state.final_reply = "Извини, я не смог корректно передать запрос дальше."
        return state
    if not _delegation_targets(state, DelegationExpert.EMOTIONAL_SUPPORT):
        return state

    _mark_node(state, "invoke_emotional_expert")

    state.selected_agents = ["emotional_support"]
    card, step_diagnostics = await extract_emotional_expert_card(state)
    state.expert_card = card
    state.diagnostics["expert"] = {
        "card": card.to_dict() if card else None,
        "llm": step_diagnostics,
    }
    if card is None:
        state.final_reply = "Извини, я не смог получить ответ эксперта."
        return state

    try:
        validate_emotional_expert_card(card)
    except ValueError as exc:
        state.final_reply = "Извини, я не смог корректно собрать помощь."
        diagnostics = dict(state.diagnostics.get("expert") or {})
        diagnostics["validation"] = {"decision": ValidationDecision.RETRY.value, "error": str(exc)}
        state.diagnostics["expert"] = diagnostics
        return state

    diagnostics = dict(state.diagnostics.get("expert") or {})
    diagnostics["validation"] = {"decision": ValidationDecision.ACCEPT.value, "error": None}
    state.diagnostics["expert"] = diagnostics
    return state


async def invoke_education_expert_node(state: FirstModuleState) -> FirstModuleState:
    if state.execution_kind is not ExecutionKind.DELEGATE:
        return state
    if state.delegation_validation is not ValidationDecision.ACCEPT:
        state.final_reply = "Извини, я не смог корректно передать запрос дальше."
        return state
    if not _delegation_targets(state, DelegationExpert.EDUCATION):
        return state

    _mark_node(state, "invoke_education_expert")

    state.selected_agents = ["education"]
    card, step_diagnostics = await extract_education_expert_card(state)
    state.expert_card = card
    state.diagnostics["expert"] = {
        "card": card.to_dict() if card else None,
        "llm": step_diagnostics,
    }
    if card is None:
        state.final_reply = "Извини, я не смог получить ответ эксперта."
        return state

    try:
        validate_education_expert_card(card)
    except ValueError as exc:
        state.final_reply = "Извини, я не смог корректно собрать объяснение."
        diagnostics = dict(state.diagnostics.get("expert") or {})
        diagnostics["validation"] = {"decision": ValidationDecision.RETRY.value, "error": str(exc)}
        state.diagnostics["expert"] = diagnostics
        return state

    diagnostics = dict(state.diagnostics.get("expert") or {})
    diagnostics["validation"] = {"decision": ValidationDecision.ACCEPT.value, "error": None}
    state.diagnostics["expert"] = diagnostics
    state.needs_clarification = False
    return state


def finalize_reply_node(state: FirstModuleState) -> FirstModuleState:
    _mark_node(state, "finalize_reply")
    if state.execution_kind is ExecutionKind.DELEGATE and state.expert_card is not None:
        if isinstance(state.expert_card, EmotionalExpertCard):
            state.final_reply = build_emotional_reply(state.expert_card)
            state.needs_clarification = state.expert_card.needs_more_info is BinaryChoice.YES
        elif isinstance(state.expert_card, EducationExpertCard):
            state.final_reply = build_education_reply(state.expert_card)
            state.needs_clarification = False
    if not state.final_reply:
        state.final_reply = build_finish_reply(state.user_message)
    return state
