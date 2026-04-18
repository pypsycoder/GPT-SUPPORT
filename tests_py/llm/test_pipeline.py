import pytest

from app.llm.langgraph_supervisor import engine as graph_engine
from app.llm.langgraph_supervisor.models import (
    BinaryChoice,
    DelegationCard,
    DelegationExpert,
    EmotionalExpertCard,
    IntakeCard,
)
from app.llm.pipeline.pipeline import LLMPipeline
from app.llm.pipeline.types import LLMRequest
from app.llm.supervisor.models import CurrentState


@pytest.fixture(autouse=True)
def _disable_compiled_graph(monkeypatch):
    monkeypatch.setattr(graph_engine, "_COMPILED_GRAPH", False)


@pytest.mark.asyncio
async def test_pipeline_greeting_opens_intake_without_legacy_router_fields(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="не обозначена",
                context="пользователь начал разговор",
                needs_clarification=BinaryChoice.YES,
                question="Что хотел бы обсудить?",
                ready_to_delegate=BinaryChoice.NO,
                rationale="Нужен открывающий вопрос.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)

    response = await LLMPipeline().process(
        LLMRequest(
            patient_id=1,
            user_input="привет",
            source="text",
        )
    )

    assert response.response == "Привет. Что хотел бы обсудить?"
    assert response.supervisor_state["pending_question"]["question_text"] == "Что хотел бы обсудить?"
    assert response.supervisor_state["needs_clarification"] is True
    assert response.diagnostics["supervisor"]["intake"]["card"]["problem"] == "не обозначена"
    assert "goal_analysis" not in response.diagnostics["supervisor"]
    assert "response_mode" not in response.diagnostics["supervisor"]


@pytest.mark.asyncio
async def test_pipeline_negative_affect_asks_single_question_without_coping(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="грусть",
                context="причина пока не названа",
                needs_clarification=BinaryChoice.YES,
                question="От чего тебе грустно?",
                ready_to_delegate=BinaryChoice.NO,
                rationale="Нужен один уточняющий вопрос.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)

    response = await LLMPipeline().process(
        LLMRequest(
            patient_id=1,
            user_input="мне грустно",
            source="text",
        )
    )

    assert response.response == "Сочувствую. От чего тебе грустно?"
    assert "вдох" not in response.response.lower()
    assert "выдох" not in response.response.lower()
    assert response.supervisor_state["pending_question"]["question_text"] == "От чего тебе грустно?"


@pytest.mark.asyncio
async def test_pipeline_uses_emotional_expert_after_delegation(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="страх перед диализом",
                context="предстоящий диализ",
                needs_clarification=BinaryChoice.NO,
                question="нет",
                ready_to_delegate=BinaryChoice.YES,
                rationale="Контекста уже достаточно.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    async def fake_extract_delegation_card(state):
        return (
            DelegationCard(
                expert=DelegationExpert.EMOTIONAL_SUPPORT,
                task="помочь справиться со страхом перед процедурой",
                rationale="Нужна эмоциональная поддержка.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    async def fake_extract_expert_card(state):
        return (
            EmotionalExpertCard(
                support="Я рядом.",
                step_now="Попробуй назвать, что в предстоящем диализе пугает сильнее всего.",
                follow_up="нет",
                needs_more_info=BinaryChoice.NO,
                rationale="Сначала поддержка, потом один шаг.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_delegation_card", fake_extract_delegation_card)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_emotional_expert_card", fake_extract_expert_card)

    response = await LLMPipeline().process(
        LLMRequest(
            patient_id=1,
            user_input="боюсь диализа",
            source="text",
            supervisor_state=CurrentState().to_dict(),
        )
    )

    assert response.response == "Я рядом. Попробуй назвать, что в предстоящем диализе пугает сильнее всего."
    assert response.supervisor_state["pending_question"] is None
    assert response.supervisor_state["last_selected_agents"] == ["emotional_support"]
    assert response.diagnostics["supervisor"]["delegation"]["card"]["expert"] == "эмоциональная_поддержка"
    assert response.diagnostics["supervisor"]["expert"]["card"]["support"] == "Я рядом."


@pytest.mark.asyncio
async def test_pipeline_raises_if_intake_analysis_fails_after_retries(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            None,
            {
                "attempts_total": 3,
                "succeeded_on_attempt": None,
                "final_status": "failed_after_retries",
                "failures": [{"attempt": 1, "error_message": "missing required fields"}],
            },
        )

    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)

    with pytest.raises(Exception) as exc_info:
        await LLMPipeline().process(
            LLMRequest(
                patient_id=1,
                user_input="мне тревожно",
                source="text",
            )
        )

    assert "supervisor intake analysis failed after 3 attempts" in str(exc_info.value)
