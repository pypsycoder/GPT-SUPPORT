import pytest

from app.llm.langgraph_supervisor import (
    BinaryChoice,
    EmotionalExpertCard,
    ExecutionKind,
    FirstModuleInput,
    run_first_module,
)
from app.llm.langgraph_supervisor import engine as graph_engine
from app.llm.pipeline.stages.supervisor import _build_updated_state
from app.llm.supervisor.models import CurrentState, PendingQuestion


def test_build_updated_state_preserves_expert_follow_up_as_pending_question():
    class GraphState:
        intake_card = None
        expert_card = EmotionalExpertCard(
            support="Я рядом.",
            step_now="Сделай медленный выдох.",
            follow_up="Когда впервые ощутили грусть?",
            needs_more_info=BinaryChoice.YES,
            rationale="нужно уточнить длительность состояния",
        )
        execution_kind = ExecutionKind.DELEGATE
        user_question = None
        needs_clarification = True
        selected_agents = ["emotional_support"]

    updated = _build_updated_state(CurrentState(), GraphState())

    assert updated.pending_question is not None
    assert updated.pending_question.reason == "expert"
    assert updated.pending_question.question_text == "Когда впервые ощутили грусть?"
    assert updated.last_selected_agents == ["emotional_support"]
    assert updated.needs_clarification is True


@pytest.mark.asyncio
async def test_first_module_routes_expert_follow_up_answer_back_to_expert(monkeypatch):
    async def fake_extract_expert_card(state):
        return (
            EmotionalExpertCard(
                support="Понял вас.",
                step_now="Это уже важная деталь, спасибо.",
                follow_up="нет",
                needs_more_info=BinaryChoice.NO,
                rationale="ответ пользователя уже дополнил контекст",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr(graph_engine, "_COMPILED_GRAPH", False)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_emotional_expert_card", fake_extract_expert_card)

    state = await run_first_module(
        FirstModuleInput(
            user_message="уже пару часов",
            current_state=CurrentState(
                goal="чувствуется грусть",
                slots={"intake_context": "причина пользователю не известна"},
                pending_question=PendingQuestion(
                    slot_name="expert_follow_up",
                    question_text="Когда впервые ощутили грусть?",
                    expected_kind="free_text",
                    attempts=1,
                    reason="expert",
                ),
                last_selected_agents=["emotional_support"],
                needs_clarification=True,
            ),
            message_type="short_answer",
            model_tier="lite",
        )
    )

    assert state.execution_kind is ExecutionKind.DELEGATE
    assert state.intake_card is not None
    assert state.intake_card.ready_to_delegate is BinaryChoice.YES
    assert "на вопрос «Когда впервые ощутили грусть?»: уже пару часов" in state.intake_card.context
    assert state.delegation_card is not None
    assert state.delegation_card.expert.value == "эмоциональная_поддержка"
    assert state.final_reply == "Понял вас.\nЭто уже важная деталь, спасибо."
