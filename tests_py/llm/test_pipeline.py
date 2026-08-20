import pytest

from app.llm.langgraph_supervisor import engine as graph_engine
from app.llm.langgraph_supervisor.models import (
    BinaryChoice,
    DelegationCard,
    DelegationExpert,
    EducationExpertCard,
    EmotionalExpertCard,
    IntakeCard,
)
from app.llm.pipeline.pipeline import LLMPipeline
from app.llm.pipeline.types import LLMRequest
from app.llm.router import ModelTier, RequestType, RouterResult
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
    assert [stage["name"] for stage in response.diagnostics["stages"]] == [
        "boundary_guard",
        "classification",
        "data_entry",
        "supervisor",
        "memory_write",
    ]


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

    # Части карточки эксперта склеиваются переносом строки, а не пробелом.
    assert response.response == "Я рядом.\nПопробуй назвать, что в предстоящем диализе пугает сильнее всего."
    assert response.supervisor_state["pending_question"] is None
    assert response.supervisor_state["last_selected_agents"] == ["emotional_support"]
    assert response.diagnostics["supervisor"]["delegation"]["card"]["expert"] == "эмоциональная_поддержка"
    assert response.diagnostics["supervisor"]["expert"]["card"]["support"] == "Я рядом."


@pytest.mark.asyncio
async def test_pipeline_uses_education_expert_after_delegation(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="не понимаю, почему после диализа такая слабость",
                context="после диализа бывает слабость, пользователь хочет понять, что это может значить",
                needs_clarification=BinaryChoice.NO,
                question="нет",
                ready_to_delegate=BinaryChoice.YES,
                rationale="Контекста достаточно для передачи дальше.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    async def fake_extract_delegation_card(state):
        return (
            DelegationCard(
                expert=DelegationExpert.EDUCATION,
                task="коротко объяснить тему простыми словами и предложить релевантный урок",
                rationale="Есть локальный educational grounding и явный запрос на объяснение.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    async def fake_extract_education_card(state):
        return (
            EducationExpertCard(
                explanation="После диализа слабость может ощущаться сильнее из-за самой нагрузки процедуры и восстановления после нее.",
                cta_type="lesson",
                cta_label="Слабость после диализа",
                cta_target={"lesson_id": 7, "lesson_code": "07_post_dialysis_fatigue"},
                rationale="Есть прямой lesson match в локальном контенте.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_delegation_card", fake_extract_delegation_card)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_education_expert_card", fake_extract_education_card)

    response = await LLMPipeline().process(
        LLMRequest(
            patient_id=1,
            user_input="объясни, почему после диализа такая слабость",
            source="text",
            supervisor_state=CurrentState().to_dict(),
        )
    )

    assert response.response == (
        "После диализа слабость может ощущаться сильнее из-за самой нагрузки процедуры и восстановления после нее.\n"
        "Если хочешь, можно посмотреть урок «Слабость после диализа»."
    )
    assert response.supervisor_state["pending_question"] is None
    assert response.supervisor_state["last_selected_agents"] == ["education"]
    assert response.diagnostics["supervisor"]["delegation"]["card"]["expert"] == "education"
    assert response.diagnostics["supervisor"]["expert"]["card"]["cta_target"]["lesson_code"] == "07_post_dialysis_fatigue"


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


@pytest.mark.asyncio
async def test_pipeline_keeps_safety_requests_on_current_runtime(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="кризис",
                context="пользователь говорит, что ему очень плохо",
                needs_clarification=BinaryChoice.NO,
                question="нет",
                ready_to_delegate=BinaryChoice.NO,
                rationale="нужно завершить ответом без уточнений",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)

    response = await LLMPipeline().process(
        LLMRequest(
            patient_id=1,
            user_input="мне очень плохо",
            source="text",
            router_result=RouterResult(
                request_type=RequestType.SAFETY,
                model_tier=ModelTier.PRO,
                domain_hint="emotion",
                priority=3,
            ),
        )
    )

    assert response.response.startswith("Я рядом.")
    assert "8-800-2000-122" in response.response
    assert response.diagnostics["supervisor"]["request_type"] == "safety"
