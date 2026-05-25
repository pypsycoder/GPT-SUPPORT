"""Compatibility smoke tests for supervisor exports."""

from app.llm.router import ModelTier, RequestType, RouterResult
from app.llm.supervisor import AmbiguityType, Supervisor, should_use_supervisor


def test_supervisor_compat_returns_clarification_for_vague_message():
    decision = Supervisor().analyze("плохо")

    assert decision.needs_clarification is True
    assert decision.ambiguity_type == AmbiguityType.VAGUE_GOAL
    assert decision.clarification_question is not None


def test_should_use_supervisor_skips_safety_requests():
    classification = RouterResult(
        request_type=RequestType.SAFETY,
        model_tier=ModelTier.MAX,
        domain_hint=None,
        priority=3,
    )

    assert should_use_supervisor("не хочу жить", classification) is False
