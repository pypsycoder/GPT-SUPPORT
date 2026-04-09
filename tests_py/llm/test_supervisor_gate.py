"""Tests for clarify-before-delegate behavior."""

from app.llm.supervisor import CurrentState, PendingQuestion, SupervisorOrchestrator


def _analysis(
    *,
    goal: str | None,
    goal_status: str,
    needs_clarification: bool,
    clarification_question: str | None = None,
    clarification_reason: str = "resolved",
    enough_context_for_support: bool = True,
    enough_context_for_plan: bool = False,
    state_hints: dict | None = None,
) -> dict:
    return {
        "used": True,
        "goal": goal,
        "goal_status": goal_status,
        "reason": goal_status,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "clarification_reason": clarification_reason,
        "enough_context_for_support": enough_context_for_support,
        "enough_context_for_plan": enough_context_for_plan,
        "state_hints": state_hints or {},
    }


def test_orchestrator_asks_one_clarifying_question_when_goal_missing():
    result = SupervisorOrchestrator().handle_message(
        "привет",
        CurrentState(),
        goal_resolution=_analysis(
            goal=None,
            goal_status="context_missing",
            needs_clarification=True,
            clarification_question="Что сейчас беспокоит тебя больше всего?",
            clarification_reason="context_missing",
            enough_context_for_support=False,
            enough_context_for_plan=False,
        ),
    )

    assert result.needs_clarification is True
    assert result.selected_agents == []
    assert result.updated_state.pending_question is not None
    assert result.updated_state.pending_question.slot_name == "goal"
    assert result.reply == "Что сейчас беспокоит тебя больше всего?"
    assert result.diagnostics["response_mode"] == "clarify_only"


def test_orchestrator_asks_context_clarification_for_generic_anxiety():
    result = SupervisorOrchestrator().handle_message(
        "мне тревожно",
        CurrentState(),
        goal_resolution=_analysis(
            goal=None,
            goal_status="generic_distress",
            needs_clarification=True,
            clarification_question="Из-за чего тревога сейчас сильнее всего?",
            clarification_reason="generic_distress",
            enough_context_for_support=False,
            enough_context_for_plan=False,
            state_hints={"signals": ["distress"]},
        ),
    )

    assert result.needs_clarification is True
    assert result.selected_agents == []
    assert result.updated_state.pending_question is not None
    assert "?" in result.reply
    assert "выдох" in result.reply.lower()
    assert result.updated_state.clarification_streak == 1
    assert result.diagnostics["response_mode"] == "hybrid_clarify"
    assert result.diagnostics["context_sufficiency"] == {"support": False, "plan": False}


def test_orchestrator_delegates_when_anxiety_has_context():
    result = SupervisorOrchestrator().handle_message(
        "мне тревожно перед диализом",
        CurrentState(),
        goal_resolution=_analysis(
            goal="тревога перед диализом",
            goal_status="resolved",
            needs_clarification=False,
            clarification_reason="resolved",
            enough_context_for_support=True,
            enough_context_for_plan=True,
            state_hints={"signals": ["distress", "dialysis_context"], "facts": ["mentioned_dialysis"]},
        ),
    )

    assert result.needs_clarification is False
    assert "emotional_support" in result.selected_agents
    assert result.diagnostics["response_mode"] == "direct_support"


def test_orchestrator_delegates_when_goal_is_clear():
    state = CurrentState(domain="health", intent="plan", goal="получить следующий шаг")

    result = SupervisorOrchestrator().handle_message(
        "Что делать перед диализом?",
        state,
        goal_resolution=_analysis(
            goal="подготовиться к диализу",
            goal_status="resolved",
            needs_clarification=False,
            clarification_reason="resolved",
            enough_context_for_support=True,
            enough_context_for_plan=True,
            state_hints={"intent": "plan", "signals": ["dialysis_context", "needs_plan"]},
        ),
    )

    assert result.needs_clarification is False
    assert result.selected_agents
    assert result.updated_state.last_selected_agents == result.selected_agents
    assert result.diagnostics["response_mode"] == "direct_plan"


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

    result = SupervisorOrchestrator().handle_message(
        "8",
        state,
        goal_resolution=_analysis(
            goal="справиться с тревогой",
            goal_status="resolved",
            needs_clarification=False,
        ),
    )

    assert result.used_pending_answer is True
    assert result.message_type == "short_answer"
    assert result.updated_state.slots["distress_level"] == 8
    assert result.updated_state.pending_question is None


def test_orchestrator_uses_pending_free_text_answer_for_goal_slot():
    state = CurrentState(
        domain="general",
        intent="support",
        pending_question=PendingQuestion(
            slot_name="goal",
            question_text="Что сейчас беспокоит тебя больше всего?",
            expected_kind="free_text",
        ),
        needs_clarification=True,
    )

    result = SupervisorOrchestrator().handle_message(
        "предстоящий диализ",
        state,
        goal_resolution=_analysis(
            goal="переживания из-за предстоящего диализа",
            goal_status="resolved",
            needs_clarification=False,
            clarification_reason="resolved",
            enough_context_for_support=True,
            enough_context_for_plan=True,
            state_hints={"signals": ["dialysis_context"], "facts": ["mentioned_dialysis"]},
        ),
    )

    assert result.used_pending_answer is True
    assert result.message_type == "short_answer"
    assert result.updated_state.goal == "переживания из-за предстоящего диализа"
    assert result.updated_state.pending_question is None


def test_orchestrator_asks_second_clarification_for_generic_pending_goal_answer():
    state = CurrentState(
        domain="general",
        intent="support",
        pending_question=PendingQuestion(
            slot_name="goal",
            question_text="Что сейчас беспокоит тебя больше всего?",
            expected_kind="free_text",
            attempts=1,
            reason="context_missing",
        ),
        needs_clarification=True,
        clarification_streak=1,
        last_clarification_reason="context_missing",
    )

    result = SupervisorOrchestrator().handle_message(
        "мне тревожно",
        state,
        goal_resolution=_analysis(
            goal=None,
            goal_status="generic_distress",
            needs_clarification=True,
            clarification_question="Из-за чего тревога сейчас сильнее всего?",
            clarification_reason="generic_distress",
            enough_context_for_support=False,
            enough_context_for_plan=False,
            state_hints={"signals": ["distress"]},
        ),
    )

    assert result.used_pending_answer is True
    assert result.needs_clarification is True
    assert result.selected_agents == []
    assert result.updated_state.pending_question is not None
    assert result.updated_state.goal is None
    assert result.updated_state.clarification_streak == 2
    assert result.diagnostics["response_mode"] == "hybrid_clarify"


def test_orchestrator_stops_clarifying_after_cap_and_switches_to_help():
    state = CurrentState(
        domain="general",
        intent="support",
        clarification_streak=5,
        needs_clarification=True,
        signals=["distress"],
    )

    result = SupervisorOrchestrator().handle_message(
        "не знаю",
        state,
        goal_resolution=_analysis(
            goal=None,
            goal_status="generic_distress",
            needs_clarification=True,
            clarification_question="Из-за чего тревога сейчас сильнее всего?",
            clarification_reason="generic_distress",
            enough_context_for_support=False,
            enough_context_for_plan=False,
            state_hints={"signals": ["distress"]},
        ),
    )

    assert result.needs_clarification is False
    assert result.updated_state.clarification_streak == 0
    assert "emotional_support" in result.selected_agents
    assert result.diagnostics["clarification_gate"]["forced_by_cap"] is True
    assert result.diagnostics["response_mode"] == "direct_support"
