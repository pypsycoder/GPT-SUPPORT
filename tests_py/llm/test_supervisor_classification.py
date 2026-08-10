"""Tests for supervisor classification."""

from app.llm.supervisor import CurrentState, PendingQuestion
from app.llm.supervisor.classification import classify_message, detect_message_type


def test_detects_correction_before_other_types():
    state = CurrentState()
    assert detect_message_type("точнее, я про диализ", state) == "correction"


def test_detects_short_answer_only_with_pending_question():
    state = CurrentState(
        pending_question=PendingQuestion(slot_name="distress_level", question_text="?", expected_kind="scale_0_10")
    )
    assert detect_message_type("7", state) == "short_answer"
    assert detect_message_type("7", CurrentState()) == "full_message"


def test_detects_meta_message():
    assert detect_message_type("спасибо", CurrentState()) == "meta_message"


def test_detects_ugu_as_meta_message_without_pending_question():
    assert detect_message_type("угу", CurrentState(goal="разобраться с самочувствием")) == "meta_message"


def test_classifies_health_inform_message():
    result = classify_message("Объясни, почему перед диализом так тревожно", CurrentState())

    assert result["domain"] == "health"
    assert result["intent"] == "inform"
    assert "before_dialysis" in result["risk_flags"]


def test_classifies_daily_routine_plan_message():
    result = classify_message("Как выстроить режим сна на этой неделе?", CurrentState())

    assert result["domain"] == "daily_routine"
    assert result["intent"] == "plan"


def test_classifies_general_support_message():
    result = classify_message("Мне очень тяжело и плохо", CurrentState())

    assert result["domain"] == "general"
    assert result["intent"] == "support"
    assert "emotional_pain" in result["signals"]
