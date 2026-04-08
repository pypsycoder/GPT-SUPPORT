"""Tests for clarify-before-delegate behavior."""

from app.llm.supervisor import CurrentState, PendingQuestion, SupervisorOrchestrator


def test_orchestrator_asks_one_clarifying_question_when_goal_missing():
    result = SupervisorOrchestrator().handle_message("Мне плохо", CurrentState())

    assert result.needs_clarification is True
    assert result.selected_agents == []
    assert result.updated_state.pending_question is not None
    assert result.updated_state.pending_question.slot_name == "goal"


def test_orchestrator_delegates_when_goal_is_clear():
    state = CurrentState(domain="health", intent="plan", goal="получить следующий шаг")

    result = SupervisorOrchestrator().handle_message("Что делать перед диализом?", state)

    assert result.needs_clarification is False
    assert result.selected_agents
    assert result.updated_state.last_selected_agents == result.selected_agents


def test_orchestrator_uses_pending_short_answer_without_full_reclassification():
    state = CurrentState(
        domain="health",
        intent="support",
        goal="получить поддержку",
        pending_question=PendingQuestion(
            slot_name="distress_level",
            question_text="Насколько тяжело сейчас по шкале от 0 до 10?",
            expected_kind="scale_0_10",
        ),
    )

    result = SupervisorOrchestrator().handle_message("8", state)

    assert result.used_pending_answer is True
    assert result.message_type == "short_answer"
    assert result.updated_state.slots["distress_level"] == 8
    assert result.updated_state.pending_question is None
