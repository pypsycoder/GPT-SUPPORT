"""Tests for short answer handling."""

import pytest

from app.llm.supervisor import PendingQuestion, try_parse_pending_answer
from app.llm.supervisor.short_answers import (
    is_education_neutral_ack,
    is_unknown_reason_answer,
    normalize_short_answer,
)


def test_normalize_short_answer_cases():
    cases = {
        "да": ("yes_no", True),
        "нет": ("yes_no", False),
        "не знаю": ("unknown", "unknown"),
        "без понятия": ("unknown", "unknown"),
        "понятия не имею": ("unknown", "unknown"),
        "0": ("scale_0_10", 0),
        "7": ("scale_0_10", 7),
        "10": ("scale_0_10", 10),
        "иногда": ("fuzzy", "иногда"),
        "вроде": ("fuzzy", "вроде"),
    }

    for text, expected in cases.items():
        parsed = normalize_short_answer(text)
        assert parsed is not None
        assert parsed["kind"] == expected[0]
        assert parsed["value"] == expected[1]


def test_unknown_reason_answer_detects_no_cause_reply():
    assert is_unknown_reason_answer("не знаю. просто ничего не радует") is True
    assert is_unknown_reason_answer("без понятия") is True


def test_unknown_reason_answer_does_not_trigger_when_cause_is_present():
    assert is_unknown_reason_answer("не знаю, может после диализа меня накрывает") is False


def test_try_parse_pending_answer_accepts_matching_kind():
    pending = PendingQuestion(
        slot_name="distress_level",
        question_text="Насколько тяжело сейчас по шкале от 0 до 10?",
        expected_kind="scale_0_10",
    )

    parsed = try_parse_pending_answer("8", pending)

    assert parsed is not None
    assert parsed["slot_name"] == "distress_level"
    assert parsed["slot_value"] == 8


def test_try_parse_pending_answer_rejects_wrong_kind():
    pending = PendingQuestion(
        slot_name="confirm_plan",
        question_text="Это тебе подходит?",
        expected_kind="yes_no",
    )

    assert try_parse_pending_answer("7", pending) is None


def test_try_parse_pending_answer_accepts_free_text():
    pending = PendingQuestion(
        slot_name="goal",
        question_text="Что сейчас беспокоит тебя больше всего?",
        expected_kind="free_text",
    )

    parsed = try_parse_pending_answer("предстоящий диализ", pending)

    assert parsed is not None
    assert parsed["slot_name"] == "goal"
    assert parsed["slot_value"] == "предстоящий диализ"
    assert parsed["answer_kind"] == "free_text"


@pytest.mark.parametrize("text", ["круто", "супер", "класс", "Отлично!", "здорово", "хорошо"])
def test_approving_reactions_count_as_neutral_ack(text):
    """Одобрение без запроса продолжения закрывает education-сессию."""
    assert is_education_neutral_ack(text) is True


@pytest.mark.parametrize("text", ["понятно", "ясно", "ок", "понял спасибо"])
def test_existing_neutral_acks_still_work(text):
    assert is_education_neutral_ack(text) is True


@pytest.mark.parametrize(
    "text",
    ["а что ещё?", "расскажи больше", "круто, а что с калием?", "не понял", "почему так"],
)
def test_requests_to_continue_are_not_neutral_acks(text):
    assert is_education_neutral_ack(text) is False
