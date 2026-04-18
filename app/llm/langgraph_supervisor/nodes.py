"""Graph v2 nodes for intake -> delegation -> emotional expert."""

from __future__ import annotations

from app.llm.langgraph_supervisor.models import (
    BinaryChoice,
    ExecutionKind,
    FirstModuleState,
    ValidationDecision,
)

# Максимальное число ходов с уточняющими вопросами до принудительной делегации.
# При достижении лимита (и обозначенной проблеме) код форсирует DELEGATE
# независимо от того, что вернула модель — двойная защита от петель.
_MAX_CLARIFICATION_STREAK = 2
from app.llm.langgraph_supervisor.policy import (
    build_emotional_reply,
    build_finish_reply,
    build_intake_reply,
    extract_delegation_card,
    extract_emotional_expert_card,
    extract_intake_card,
    validate_delegation_card,
    validate_emotional_expert_card,
    validate_intake_card,
)


def _mark_node(state: FirstModuleState, node_name: str) -> None:
    graph_path = state.diagnostics.setdefault("graph_path", [])
    if not isinstance(graph_path, list):
        graph_path = []
        state.diagnostics["graph_path"] = graph_path
    graph_path.append(node_name)


async def intake_analyze_node(state: FirstModuleState) -> FirstModuleState:
    _mark_node(state, "intake_analyze")
    card, step_diagnostics = await extract_intake_card(state)
    state.intake_card = card
    state.diagnostics["intake"] = {
        "card": card.to_dict() if card else None,
        "llm": step_diagnostics,
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
    state.needs_clarification = card.needs_clarification is BinaryChoice.YES

    # Fix 4: кодовый предохранитель от петли уточнений.
    # Если модель всё равно вернула needs_clarification=да, но:
    #   - streak достиг лимита, И
    #   - проблема уже обозначена —
    # принудительно переходим к делегации, не спрашивая пациента ещё раз.
    if (
        card.needs_clarification is BinaryChoice.YES
        and streak >= _MAX_CLARIFICATION_STREAK
        and card.problem not in {"", "не обозначена"}
    ):
        state.execution_kind = ExecutionKind.DELEGATE
        state.needs_clarification = False
        return state

    if card.needs_clarification is BinaryChoice.YES:
        state.execution_kind = ExecutionKind.ASK
        state.user_question = card.question
        state.final_reply = build_intake_reply(card)
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
    _mark_node(state, "invoke_emotional_expert")

    if state.delegation_validation is not ValidationDecision.ACCEPT:
        state.final_reply = "Извини, я не смог корректно передать запрос дальше."
        return state

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


def finalize_reply_node(state: FirstModuleState) -> FirstModuleState:
    _mark_node(state, "finalize_reply")
    if state.execution_kind is ExecutionKind.DELEGATE and state.expert_card is not None:
        state.final_reply = build_emotional_reply(state.expert_card)
        state.needs_clarification = state.expert_card.needs_more_info is BinaryChoice.YES
    if not state.final_reply:
        state.final_reply = build_finish_reply(state.user_message)
    return state
