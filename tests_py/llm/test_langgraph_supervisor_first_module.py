import pytest

from app.llm.langgraph_supervisor import (
    BinaryChoice,
    DelegationCard,
    DelegationExpert,
    EmotionalExpertCard,
    ExecutionKind,
    FirstModuleInput,
    IntakeCard,
    ValidationDecision,
    run_first_module,
)
from app.llm.langgraph_supervisor import engine as graph_engine
from app.llm.langgraph_supervisor.policy import validate_intake_card
from app.llm.pipeline.stages.supervisor import _build_updated_state
from app.llm.supervisor.models import CurrentState, PendingQuestion


@pytest.mark.asyncio
async def test_first_module_asks_single_intake_question(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="тревога",
                context="причина пока не названа",
                needs_clarification=BinaryChoice.YES,
                question="От чего тебе тревожно?",
                ready_to_delegate=BinaryChoice.NO,
                rationale="Нужен один уточняющий вопрос.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr(graph_engine, "_COMPILED_GRAPH", False)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)

    state = await run_first_module(
        FirstModuleInput(
            user_message="мне тревожно",
            current_state=CurrentState(),
            message_type="full_message",
            model_tier="lite",
        )
    )

    assert state.intake_card is not None
    assert state.intake_validation is ValidationDecision.ACCEPT
    assert state.execution_kind is ExecutionKind.ASK
    assert state.final_reply == "Сочувствую. От чего тебе тревожно?"
    assert state.user_question == "От чего тебе тревожно?"
    assert state.diagnostics["graph_path"] == [
        "intake_analyze",
        "intake_validate",
        "intake_execute",
        "finalize_reply",
    ]


@pytest.mark.asyncio
async def test_first_module_delegates_and_uses_emotional_expert(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="страх перед диализом",
                context="предстоящий диализ. страх усиливается заранее.",
                needs_clarification=BinaryChoice.NO,
                question="нет",
                ready_to_delegate=BinaryChoice.YES,
                rationale="Контекста уже достаточно для передачи.",
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
                rationale="Сначала поддержка, потом один конкретный шаг.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr(graph_engine, "_COMPILED_GRAPH", False)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_delegation_card", fake_extract_delegation_card)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_emotional_expert_card", fake_extract_expert_card)

    state = await run_first_module(
        FirstModuleInput(
            user_message="боюсь диализа",
            current_state=CurrentState(),
            message_type="full_message",
            model_tier="lite",
        )
    )

    assert state.execution_kind is ExecutionKind.DELEGATE
    assert state.delegation_validation is ValidationDecision.ACCEPT
    assert state.selected_agents == ["emotional_support"]
    assert state.final_reply == "Я рядом. Попробуй назвать, что в предстоящем диализе пугает сильнее всего."
    assert state.diagnostics["graph_path"] == [
        "intake_analyze",
        "intake_validate",
        "intake_execute",
        "delegation_analyze",
        "delegation_validate",
        "invoke_emotional_expert",
        "finalize_reply",
    ]


@pytest.mark.asyncio
async def test_first_module_can_finish_without_delegation(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="не обозначена",
                context="мета-ответ без новой темы",
                needs_clarification=BinaryChoice.NO,
                question="нет",
                ready_to_delegate=BinaryChoice.NO,
                rationale="Новый содержательный цикл не нужен.",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr(graph_engine, "_COMPILED_GRAPH", False)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)

    state = await run_first_module(
        FirstModuleInput(
            user_message="спасибо",
            current_state=CurrentState(),
            message_type="meta_message",
            model_tier="lite",
        )
    )

    assert state.execution_kind is ExecutionKind.FINISH
    assert state.final_reply == "Пожалуйста."
    assert state.selected_agents == []


def test_validate_intake_card_disallows_delegation_without_problem():
    with pytest.raises(ValueError, match="undefined problem cannot be delegated"):
        validate_intake_card(
            IntakeCard(
                problem="не обозначена",
                context="приветствие",
                needs_clarification=BinaryChoice.NO,
                question="нет",
                ready_to_delegate=BinaryChoice.YES,
                rationale="ошибка",
            )
        )


def test_build_updated_state_preserves_accumulated_intake_context():
    current_state = CurrentState(
        goal="страх перед диализом",
        slots={"intake_context": "диализ. страх перед процедурой."},
        pending_question=PendingQuestion(
            slot_name="clarify",
            question_text="Что именно пугает?",
            expected_kind="free_text",
            attempts=1,
            reason="intake",
        ),
        needs_clarification=True,
        clarification_streak=1,
    )

    class GraphState:
        intake_card = IntakeCard(
            problem="повышение давления",
            context="во время процедуры поднимается давление.",
            needs_clarification=BinaryChoice.YES,
            question="Что происходит дальше?",
            ready_to_delegate=BinaryChoice.NO,
            rationale="контекст уточняется",
        )
        execution_kind = ExecutionKind.ASK
        user_question = "Что происходит дальше?"
        needs_clarification = True
        selected_agents = []

    updated = _build_updated_state(current_state, GraphState())

    assert updated.slots["intake_context"] == (
        "диализ. страх перед процедурой.. во время процедуры поднимается давление."
    )
