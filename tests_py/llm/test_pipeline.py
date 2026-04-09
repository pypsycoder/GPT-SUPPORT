"""Tests for pipeline integration with the stateful supervisor MVP."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.llm.agent_v2 import generate_response_v2
from app.llm.errors import LLMResponseError
from app.llm.pipeline import LLMRequest, LLMPipeline
from app.llm.router import ModelTier, RequestType, RouterResult


# _analysis_fields
def _analysis_fields(
    *,
    goal: str | None,
    goal_status: str,
    needs_clarification: bool,
    clarification_question: str | None,
    clarification_reason: str,
    enough_context_for_support: bool,
    enough_context_for_plan: bool,
    state_hints: dict | None = None,
) -> str:
    hints = state_hints or {}
    signals = ", ".join(hints.get("signals") or []) or "none"
    risk_flags = ", ".join(hints.get("risk_flags") or []) or "none"
    facts = ", ".join(hints.get("facts") or []) or "none"
    domain = hints.get("domain") or "null"
    intent = hints.get("intent") or "null"
    return "\n".join(
        [
            f"goal: {goal if goal is not None else 'null'}",
            f"goal_status: {goal_status}",
            f"needs_clarification: {'true' if needs_clarification else 'false'}",
            f"clarification_question: {clarification_question if clarification_question is not None else 'null'}",
            f"clarification_reason: {clarification_reason}",
            f"enough_context_for_support: {'true' if enough_context_for_support else 'false'}",
            f"enough_context_for_plan: {'true' if enough_context_for_plan else 'false'}",
            f"state_hints.signals: {signals}",
            f"state_hints.risk_flags: {risk_flags}",
            f"state_hints.facts: {facts}",
            f"state_hints.domain: {domain}",
            f"state_hints.intent: {intent}",
        ]
    )


class FakeSupervisorClient:
    def __init__(self, responses: list[tuple[str, int, int, int]], *, model_tier: str = "pro", account_id: str = "A1-pro"):
        self._responses = list(responses)
        self.model_tier = model_tier
        self.account_id = account_id

    async def call(self, _messages, _system_prompt):
        if not self._responses:
            raise AssertionError("No fake LLM responses left for supervisor stage")
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_pipeline_returns_direct_plan_for_contextual_distress_with_action_request(monkeypatch):
    pipeline = LLMPipeline()
    fake_client = FakeSupervisorClient(
        [
            (
                _analysis_fields(
                    goal="тревога перед диализом",
                    goal_status="resolved",
                    needs_clarification=False,
                    clarification_question=None,
                    clarification_reason="resolved",
                    enough_context_for_support=True,
                    enough_context_for_plan=True,
                    state_hints={"signals": ["distress", "dialysis_context"], "facts": ["mentioned_dialysis"]},
                ),
                20,
                8,
                50,
            ),
            ("Давай разберем, что именно тревожит тебя перед диализом, и выберем один шаг, который немного снизит напряжение уже сейчас.", 60, 30, 90),
        ],
        model_tier="lite",
        account_id="A1",
    )
    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.pool.get_available", AsyncMock(return_value=fake_client))

    response = await pipeline.process(
        LLMRequest(
            patient_id=1,
            user_input="Что делать перед диализом, мне тревожно",
            source="text",
            db=None,
        )
    )

    assert response.response
    assert response.account_id == "SUPERVISOR"
    assert response.supervisor_state is not None
    assert response.supervisor_state_delta
    assert response.diagnostics["supervisor"]["enabled"] is True
    assert response.diagnostics["supervisor"]["goal_analysis"]["goal"] == "тревога перед диализом"
    assert response.diagnostics["supervisor"]["goal_analysis"]["final_status"] == "success"
    assert response.diagnostics["supervisor"]["response_mode"] == "direct_plan"
    assert response.diagnostics["patient_context"]["skipped"] is True
    assert response.diagnostics["orchestration"]["skipped"] is True


@pytest.mark.asyncio
async def test_pipeline_uses_hybrid_clarify_for_generic_distress(monkeypatch):
    pipeline = LLMPipeline()
    fake_client = FakeSupervisorClient(
        [
            (
                _analysis_fields(
                    goal=None,
                    goal_status="generic_distress",
                    needs_clarification=True,
                    clarification_question="Из-за чего тревога сейчас сильнее всего?",
                    clarification_reason="generic_distress",
                    enough_context_for_support=False,
                    enough_context_for_plan=False,
                    state_hints={"signals": ["distress"]},
                ),
                12,
                5,
                25,
            ),
            ("Сейчас тревога и правда может давить. Попробуй на пару дыханий чуть замедлиться и сделать выдох длиннее вдоха. Из-за чего тревога сейчас сильнее всего?", 30, 18, 55),
        ]
    )
    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.pool.get_available", AsyncMock(return_value=fake_client))

    response = await pipeline.process(
        LLMRequest(
            patient_id=1,
            user_input="Мне тревожно",
            source="text",
            db=None,
        )
    )

    assert response.diagnostics["supervisor"]["response_mode"] == "hybrid_clarify"
    assert response.diagnostics["supervisor"]["context_sufficiency"] == {"support": False, "plan": False}
    assert response.diagnostics["supervisor"]["needs_clarification"] is True
    assert "выдох" in response.response.lower()
    assert response.response.endswith("?")


@pytest.mark.asyncio
async def test_pipeline_retries_invalid_field_block_then_succeeds(monkeypatch):
    pipeline = LLMPipeline()
    fake_client = FakeSupervisorClient(
        [
            ("this is not a field block", 10, 4, 20),
            (
                _analysis_fields(
                    goal="тревога перед диализом",
                    goal_status="resolved",
                    needs_clarification=False,
                    clarification_question=None,
                    clarification_reason="resolved",
                    enough_context_for_support=True,
                    enough_context_for_plan=False,
                    state_hints={"signals": ["distress", "dialysis_context"]},
                )
                + "\nСпасибо",
                10,
                4,
                20,
            ),
            (
                _analysis_fields(
                    goal=None,
                    goal_status="generic_distress",
                    needs_clarification=True,
                    clarification_question="Из-за чего тревога сейчас сильнее всего?",
                    clarification_reason="generic_distress",
                    enough_context_for_support=False,
                    enough_context_for_plan=False,
                    state_hints={"signals": ["distress"]},
                ),
                12,
                5,
                25,
            ),
            ("Сейчас тревога и правда может давить. Попробуй на пару дыханий чуть замедлиться и сделать выдох длиннее вдоха. Из-за чего тревога сейчас сильнее всего?", 30, 18, 55),
        ]
    )
    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.pool.get_available", AsyncMock(return_value=fake_client))

    response = await pipeline.process(
        LLMRequest(
            patient_id=1,
            user_input="Мне тревожно",
            source="text",
            db=None,
        )
    )

    goal_analysis = response.diagnostics["supervisor"]["goal_analysis"]
    assert goal_analysis["attempts_total"] == 3
    assert goal_analysis["succeeded_on_attempt"] == 3
    assert len(goal_analysis["failures"]) == 2
    assert goal_analysis["final_status"] == "success"
    assert goal_analysis["failures"][1]["error_message"] == "goal analysis line 13 is not a field entry"


@pytest.mark.asyncio
async def test_pipeline_fails_after_three_invalid_field_attempts(monkeypatch):
    pipeline = LLMPipeline()
    fake_client = FakeSupervisorClient(
        [
            ("not a field block", 10, 4, 20),
            ("goal: тревога\ngoal_status: resolved", 10, 4, 20),
            ("goal: тревога\nneeds_clarification: maybe", 10, 4, 20),
        ]
    )
    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.pool.get_available", AsyncMock(return_value=fake_client))

    with pytest.raises(LLMResponseError, match="goal analysis failed after 3 attempts"):
        await pipeline.process(
            LLMRequest(
                patient_id=1,
                user_input="Мне тревожно",
                source="text",
                db=None,
            )
        )


@pytest.mark.asyncio
async def test_pipeline_retries_when_anchored_followup_is_labeled_generic_distress(monkeypatch):
    pipeline = LLMPipeline()
    fake_client = FakeSupervisorClient(
        [
            (
                _analysis_fields(
                    goal="ожидание диализа",
                    goal_status="generic_distress",
                    needs_clarification=True,
                    clarification_question="Что сейчас тревожит сильнее всего?",
                    clarification_reason="generic_distress",
                    enough_context_for_support=False,
                    enough_context_for_plan=False,
                    state_hints={"signals": ["distress", "dialysis_context"]},
                ),
                10,
                5,
                20,
            ),
            (
                _analysis_fields(
                    goal="ожидание диализа",
                    goal_status="context_missing",
                    needs_clarification=True,
                    clarification_question="Что в предстоящем диализе тревожит тебя сильнее всего?",
                    clarification_reason="context_missing",
                    enough_context_for_support=False,
                    enough_context_for_plan=False,
                    state_hints={"signals": ["distress", "dialysis_context"], "facts": ["mentioned_dialysis"]},
                ),
                12,
                6,
                24,
            ),
            ("Ожидание диализа и правда может сильно напрягать. Попробуй на пару дыханий чуть замедлиться. Что в предстоящем диализе тревожит тебя сильнее всего?", 18, 12, 31),
        ]
    )
    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.pool.get_available", AsyncMock(return_value=fake_client))

    response = await pipeline.process(
        LLMRequest(
            patient_id=1,
            user_input="жду диализ",
            source="text",
            supervisor_state={
                "domain": "health",
                "intent": "support",
                "needs_clarification": True,
                "clarification_streak": 1,
                "pending_question": {
                    "slot_name": "goal",
                    "question_text": "Что именно тревожит сейчас?",
                    "expected_kind": "free_text",
                    "attempts": 1,
                    "reason": "generic_distress",
                },
            },
            db=None,
        )
    )

    goal_analysis = response.diagnostics["supervisor"]["goal_analysis"]
    assert goal_analysis["attempts_total"] == 2
    assert goal_analysis["succeeded_on_attempt"] == 2
    assert goal_analysis["failures"][0]["error_message"] == "anchored follow-up cannot be labeled generic_distress"
    assert goal_analysis["goal_status"] == "context_missing"
    assert response.diagnostics["supervisor"]["response_mode"] == "clarify_only"
    assert response.supervisor_state["pending_question"]["question_text"] == "Что в предстоящем диализе тревожит тебя сильнее всего?"


@pytest.mark.asyncio
async def test_pipeline_retries_when_anchored_clarification_drifts_into_side_detail(monkeypatch):
    pipeline = LLMPipeline()
    fake_client = FakeSupervisorClient(
        [
            (
                _analysis_fields(
                    goal="ожидание диализа",
                    goal_status="context_missing",
                    needs_clarification=True,
                    clarification_question="С какой частотой тебе требуется процедура диализа?",
                    clarification_reason="context_missing",
                    enough_context_for_support=False,
                    enough_context_for_plan=False,
                    state_hints={"signals": ["distress", "dialysis_context"], "facts": ["mentioned_dialysis"]},
                ),
                10,
                5,
                20,
            ),
            (
                _analysis_fields(
                    goal="ожидание диализа",
                    goal_status="context_missing",
                    needs_clarification=True,
                    clarification_question="Что в предстоящем диализе тревожит тебя сильнее всего?",
                    clarification_reason="context_missing",
                    enough_context_for_support=False,
                    enough_context_for_plan=False,
                    state_hints={"signals": ["distress", "dialysis_context"], "facts": ["mentioned_dialysis"]},
                ),
                12,
                6,
                24,
            ),
            ("Ожидание диализа и правда может сильно напрягать. Попробуй на пару дыханий чуть замедлиться. Что в предстоящем диализе тревожит тебя сильнее всего?", 18, 12, 31),
        ]
    )
    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.pool.get_available", AsyncMock(return_value=fake_client))

    response = await pipeline.process(
        LLMRequest(
            patient_id=1,
            user_input="жду диализ",
            source="text",
            supervisor_state={
                "domain": "health",
                "intent": "support",
                "needs_clarification": True,
                "clarification_streak": 1,
                "pending_question": {
                    "slot_name": "goal",
                    "question_text": "Что именно тревожит сейчас?",
                    "expected_kind": "free_text",
                    "attempts": 1,
                    "reason": "generic_distress",
                },
            },
            db=None,
        )
    )

    goal_analysis = response.diagnostics["supervisor"]["goal_analysis"]
    assert goal_analysis["attempts_total"] == 2
    assert goal_analysis["succeeded_on_attempt"] == 2
    assert goal_analysis["failures"][0]["error_message"] == "anchored clarification question drifted into side detail"
    assert response.supervisor_state["pending_question"]["question_text"] == "Что в предстоящем диализе тревожит тебя сильнее всего?"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_input", "goal"),
    [
        ("жду диализа", "переживания из-за ожидания диализа"),
        ("перед диализом", "тревога перед диализом"),
        ("не выпил таблетки", "тревога из-за пропущенных таблеток"),
    ],
)
async def test_pipeline_handles_short_anchored_followup_without_format_crash(monkeypatch, user_input, goal):
    pipeline = LLMPipeline()
    fake_client = FakeSupervisorClient(
        [
            (
                _analysis_fields(
                    goal=goal,
                    goal_status="resolved",
                    needs_clarification=False,
                    clarification_question=None,
                    clarification_reason="resolved",
                    enough_context_for_support=True,
                    enough_context_for_plan=False,
                    state_hints={"signals": ["distress"], "facts": ["anchored_followup"]},
                ),
                11,
                6,
                22,
            ),
            ("Давай попробуем опереться на это и немного снизить напряжение прямо сейчас.", 18, 12, 31),
        ]
    )
    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.pool.get_available", AsyncMock(return_value=fake_client))

    response = await pipeline.process(
        LLMRequest(
            patient_id=1,
            user_input=user_input,
            source="text",
            supervisor_state={
                "domain": "health",
                "intent": "support",
                "needs_clarification": True,
                "clarification_streak": 1,
                "pending_question": {
                    "slot_name": "goal",
                    "question_text": "Что именно вызывает тревогу?",
                    "expected_kind": "free_text",
                    "attempts": 1,
                    "reason": "generic_distress",
                },
            },
            db=None,
        )
    )

    assert response.response
    assert response.diagnostics["supervisor"]["goal_analysis"]["goal"] == goal
    assert response.diagnostics["supervisor"]["goal_analysis"]["final_status"] == "success"
    assert response.diagnostics["supervisor"]["response_mode"] == "direct_support"
    assert response.supervisor_state["pending_question"] is None


@pytest.mark.asyncio
async def test_pipeline_handles_pending_question_short_answer(monkeypatch):
    pipeline = LLMPipeline()
    fake_client = FakeSupervisorClient(
        [
            (
                _analysis_fields(
                    goal="справиться с тревогой",
                    goal_status="resolved",
                    needs_clarification=False,
                    clarification_question=None,
                    clarification_reason="resolved",
                    enough_context_for_support=True,
                    enough_context_for_plan=False,
                    state_hints={},
                ),
                10,
                5,
                25,
            ),
            ("Спасибо. По шкале это уже выглядит заметно тяжело. Давай попробуем один спокойный шаг прямо сейчас.", 30, 18, 55),
        ]
    )
    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.pool.get_available", AsyncMock(return_value=fake_client))

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
async def test_generate_response_v2_preserves_old_contract_and_exposes_state(monkeypatch):
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    fake_client = FakeSupervisorClient(
        [
            (
                _analysis_fields(
                    goal=None,
                    goal_status="generic_distress",
                    needs_clarification=True,
                    clarification_question="Из-за чего тревога сейчас сильнее всего?",
                    clarification_reason="generic_distress",
                    enough_context_for_support=False,
                    enough_context_for_plan=False,
                    state_hints={"signals": ["distress"]},
                ),
                15,
                7,
                40,
            ),
            ("Сейчас тревога и правда может давить. Попробуй на пару дыханий чуть замедлиться и сделать выдох длиннее вдоха. Из-за чего тревога сейчас сильнее всего?", 32, 20, 60),
        ]
    )
    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.pool.get_available", AsyncMock(return_value=fake_client))

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
