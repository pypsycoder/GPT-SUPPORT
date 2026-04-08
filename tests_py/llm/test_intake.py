from __future__ import annotations

import pytest

from app.llm.intake import analyze_help_intake
from app.llm.router import ModelTier, RequestType, RouterResult


pytestmark = [pytest.mark.unit]


def test_analyze_help_intake_extracts_problem_intent_and_context():
    result = analyze_help_intake(
        user_input="Мне тревожно перед диализом, хочу справиться с тревогой.",
        router_result=RouterResult(
            request_type=RequestType.EMOTIONAL,
            model_tier=ModelTier.PRO,
            domain_hint="emotion",
            priority=2,
        ),
        parser_mood="bad",
        parser_domain_hints=["emotion"],
    )

    assert result.is_help_request is True
    assert result.primary_problem == "emotional_distress"
    assert result.patient_intent == "emotional_support"
    assert "before_dialysis" in result.context_factors
    assert result.information_sufficient is True
    assert result.clarification_needed is False


def test_analyze_help_intake_marks_clarification_for_multi_problem_without_clear_intent():
    result = analyze_help_intake(
        user_input="Плохо спал ночью, сегодня разбит и тревожно.",
        router_result=RouterResult(
            request_type=RequestType.SIMPLE,
            model_tier=ModelTier.PRO,
            domain_hint="sleep",
            priority=1,
        ),
        parser_mood="bad",
        parser_domain_hints=["sleep", "emotion"],
    )

    assert result.is_help_request is True
    assert result.primary_problem == "sleep_problem"
    assert result.patient_intent is None
    assert result.information_sufficient is False
    assert result.clarification_needed is True
    assert result.clarification_reason == "multiple_problems_unclear_intent"


def test_analyze_help_intake_skips_help_clarification_for_content_request():
    result = analyze_help_intake(
        user_input="Что почитать про сон?",
        router_result=RouterResult(
            request_type=RequestType.SIMPLE,
            model_tier=ModelTier.LITE,
            domain_hint="sleep",
            priority=1,
        ),
        parser_mood=None,
        parser_domain_hints=["sleep"],
    )

    assert result.message_kind == "content_request"
    assert result.is_help_request is False
    assert result.patient_intent == "education_material"
    assert result.information_sufficient is True
    assert result.clarification_needed is False
