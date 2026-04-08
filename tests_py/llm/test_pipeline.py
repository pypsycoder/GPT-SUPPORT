"""Tests for pipeline integration with the stateful supervisor MVP."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.llm.agent_v2 import generate_response_v2
from app.llm.pipeline import LLMPipeline, LLMRequest
from app.llm.router import ModelTier, RequestType, RouterResult


@pytest.mark.asyncio
async def test_pipeline_returns_supervisor_response_for_normal_text():
    pipeline = LLMPipeline()
    request = LLMRequest(
        patient_id=1,
        user_input="Что делать перед диализом, мне тревожно",
        source="text",
        db=None,
    )

    response = await pipeline.process(request)

    assert response.response
    assert response.account_id == "SUPERVISOR"
    assert response.supervisor_state is not None
    assert response.supervisor_state_delta
    assert response.diagnostics["supervisor"]["enabled"] is True
    assert response.diagnostics["patient_context"]["skipped"] is True
    assert response.diagnostics["orchestration"]["skipped"] is True


@pytest.mark.asyncio
async def test_pipeline_handles_pending_question_short_answer():
    pipeline = LLMPipeline()
    request = LLMRequest(
        patient_id=1,
        user_input="7",
        source="text",
        supervisor_state={
            "domain": "health",
            "intent": "support",
            "goal": "получить поддержку",
            "pending_question": {
                "slot_name": "distress_level",
                "question_text": "Насколько тяжело сейчас по шкале от 0 до 10?",
                "expected_kind": "scale_0_10",
                "attempts": 1,
            },
        },
        db=None,
    )

    response = await pipeline.process(request)

    assert response.supervisor_state["slots"]["distress_level"] == 7
    assert response.supervisor_state["pending_question"] is None
    assert response.diagnostics["supervisor"]["used_pending_answer"] is True


@pytest.mark.asyncio
async def test_generate_response_v2_preserves_old_contract_and_exposes_state():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    result = await generate_response_v2(
        patient_id=1,
        user_input="Мне очень тяжело",
        router_result=RouterResult(
            request_type=RequestType.SIMPLE,
            model_tier=ModelTier.PRO,
            domain_hint=None,
            priority=1,
        ),
        context={"source": "text"},
        db=db,
    )

    assert "response" in result
    assert "supervisor_state" in result
    assert "supervisor_state_delta" in result
    assert result["account_id"] == "SUPERVISOR"
