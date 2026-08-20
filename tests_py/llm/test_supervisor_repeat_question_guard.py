import pytest

from app.llm.langgraph_supervisor import (
    BinaryChoice,
    DelegationCard,
    DelegationExpert,
    EmotionalExpertCard,
    ExecutionKind,
    FirstModuleInput,
    IntakeCard,
    run_first_module,
)
from app.llm.langgraph_supervisor import engine as graph_engine
from app.llm.supervisor.models import CurrentState, PendingQuestion


@pytest.mark.asyncio
async def test_first_module_delegates_when_same_clarification_question_repeats(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="чувствуется грусть",
                context="пользователь не может назвать причину",
                needs_clarification=BinaryChoice.YES,
                question="что случилось? почему вам грустно?",
                ready_to_delegate=BinaryChoice.NO,
                rationale="модель попыталась повторить тот же вопрос",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    async def fake_extract_delegation_card(state):
        return (
            DelegationCard(
                expert=DelegationExpert.EMOTIONAL_SUPPORT,
                task="дать мягкую поддержку при неопределенной грусти",
                rationale="не нужно повторять один и тот же intake-вопрос",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    async def fake_extract_expert_card(state):
        return (
            EmotionalExpertCard(
                support="Я рядом.",
                step_now="Расскажи, как эта грусть влияет на твой день сейчас.",
                follow_up="нет",
                needs_more_info=BinaryChoice.NO,
                rationale="можно помогать без повторения intake-вопроса",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr(graph_engine, "_COMPILED_GRAPH", False)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_delegation_card", fake_extract_delegation_card)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_emotional_expert_card", fake_extract_expert_card)

    state = await run_first_module(
        FirstModuleInput(
            user_message="не знаю. просто ничего не радует",
            current_state=CurrentState(
                goal="чувствуется грусть",
                slots={"intake_context": "нет"},
                pending_question=PendingQuestion(
                    slot_name="clarify",
                    question_text="что случилось? почему вам грустно?",
                    expected_kind="free_text",
                    attempts=1,
                    reason="intake",
                ),
                needs_clarification=True,
                clarification_streak=1,
            ),
            message_type="full_message",
            model_tier="lite",
        )
    )

    assert state.execution_kind is ExecutionKind.DELEGATE
    assert state.selected_agents == ["emotional_support"]
    assert state.needs_clarification is False
    assert state.final_reply == "Я рядом.\nРасскажи, как эта грусть влияет на твой день сейчас."
