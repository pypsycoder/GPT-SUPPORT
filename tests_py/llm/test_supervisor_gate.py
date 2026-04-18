import pytest

from app.llm.langgraph_supervisor.models import (
    BinaryChoice,
    DelegationCard,
    DelegationExpert,
    EmotionalExpertCard,
    ExecutionKind,
    IntakeCard,
)
from app.llm.pipeline.stages.supervisor import SupervisorStage
from app.llm.pipeline.types import LLMRequest, PipelineContext
from app.llm.router import ModelTier, RequestType, RouterResult
from app.llm.supervisor.models import CurrentState


def _context(user_input: str, *, supervisor_state: dict | None = None) -> PipelineContext:
    return PipelineContext(
        request=LLMRequest(
            patient_id=1,
            user_input=user_input,
            source="text",
            supervisor_state=supervisor_state,
        ),
        classification=RouterResult(
            request_type=RequestType.EMOTIONAL,
            model_tier=ModelTier.LITE,
            domain_hint="emotion",
            priority=2,
        ),
        supervisor_state=supervisor_state or {},
        diagnostics={},
    )


@pytest.mark.asyncio
async def test_supervisor_stage_sets_pending_question_for_intake(monkeypatch):
    class FakeGraphState:
        intake_card = IntakeCard(
            problem="грусть",
            context="причина пока не названа",
            needs_clarification=BinaryChoice.YES,
            question="От чего тебе грустно?",
            ready_to_delegate=BinaryChoice.NO,
            rationale="Нужен один вопрос.",
        )
        delegation_card = None
        expert_card = None
        execution_kind = ExecutionKind.ASK
        user_question = "От чего тебе грустно?"
        final_reply = "Сочувствую. От чего тебе грустно?"
        needs_clarification = True
        selected_agents = []
        diagnostics = {
            "graph_path": ["intake_analyze", "intake_validate", "intake_execute"],
            "intake": {
                "card": intake_card.to_dict(),
                "llm": {"final_status": "success", "succeeded_on_attempt": 1},
            },
            "delegation": {},
            "expert": {},
        }
        total_tokens_input = 10
        total_tokens_output = 5
        total_latency_ms = 20
        account_ids = ["A1"]
        actual_model_tiers = ["lite"]

    async def fake_run_first_module(payload):
        return FakeGraphState()

    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.run_first_module", fake_run_first_module)

    context = await SupervisorStage().process(_context("мне грустно"))

    assert context.response_draft == "Сочувствую. От чего тебе грустно?"
    assert context.supervisor_state["pending_question"]["question_text"] == "От чего тебе грустно?"
    assert context.supervisor_state["needs_clarification"] is True
    assert context.diagnostics["supervisor"]["intake"]["card"]["problem"] == "грусть"
    assert "goal_analysis" not in context.diagnostics["supervisor"]


@pytest.mark.asyncio
async def test_supervisor_stage_uses_expert_output_for_final_reply(monkeypatch):
    class FakeGraphState:
        intake_card = IntakeCard(
            problem="страх перед диализом",
            context="предстоящий диализ",
            needs_clarification=BinaryChoice.NO,
            question="нет",
            ready_to_delegate=BinaryChoice.YES,
            rationale="Можно передавать дальше.",
        )
        delegation_card = DelegationCard(
            expert=DelegationExpert.EMOTIONAL_SUPPORT,
            task="помочь справиться со страхом перед процедурой",
            rationale="Нужна эмоциональная поддержка.",
        )
        expert_card = EmotionalExpertCard(
            support="Я рядом.",
            step_now="Попробуй назвать, что пугает сильнее всего.",
            follow_up="нет",
            needs_more_info=BinaryChoice.NO,
            rationale="Один шаг без лишнего копинга.",
        )
        execution_kind = ExecutionKind.DELEGATE
        user_question = None
        final_reply = "Я рядом. Попробуй назвать, что пугает сильнее всего."
        needs_clarification = False
        selected_agents = ["emotional_support"]
        diagnostics = {
            "graph_path": [
                "intake_analyze",
                "intake_validate",
                "intake_execute",
                "delegation_analyze",
                "delegation_validate",
                "invoke_emotional_expert",
                "finalize_reply",
            ],
            "intake": {
                "card": intake_card.to_dict(),
                "llm": {"final_status": "success", "succeeded_on_attempt": 1},
            },
            "delegation": {
                "card": delegation_card.to_dict(),
                "llm": {"final_status": "success", "succeeded_on_attempt": 1},
            },
            "expert": {
                "card": expert_card.to_dict(),
                "llm": {"final_status": "success", "succeeded_on_attempt": 1},
            },
        }
        total_tokens_input = 20
        total_tokens_output = 15
        total_latency_ms = 40
        account_ids = ["A1", "A1", "A1"]
        actual_model_tiers = ["lite", "lite", "lite"]

    async def fake_run_first_module(payload):
        return FakeGraphState()

    monkeypatch.setattr("app.llm.pipeline.stages.supervisor.run_first_module", fake_run_first_module)

    context = await SupervisorStage().process(_context("боюсь диализа", supervisor_state=CurrentState().to_dict()))

    assert context.response_draft == "Я рядом. Попробуй назвать, что пугает сильнее всего."
    assert context.supervisor_state["pending_question"] is None
    assert context.supervisor_state["last_selected_agents"] == ["emotional_support"]
    assert context.diagnostics["supervisor"]["delegation"]["card"]["expert"] == "эмоциональная_поддержка"
    assert context.diagnostics["supervisor"]["expert"]["card"]["step_now"] == "Попробуй назвать, что пугает сильнее всего."
