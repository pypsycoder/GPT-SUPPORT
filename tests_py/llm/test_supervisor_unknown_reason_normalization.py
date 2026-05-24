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
async def test_first_module_normalizes_unknown_reason_answer_and_delegates(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="не обозначена",
                context="пользователь чувствует грусть, но не указал конкретной причины",
                needs_clarification=BinaryChoice.YES,
                question="что случилось? почему вам грустно?",
                ready_to_delegate=BinaryChoice.NO,
                rationale="нужна причина грусти",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    async def fake_extract_delegation_card(state):
        return (
            DelegationCard(
                expert=DelegationExpert.EMOTIONAL_SUPPORT,
                task="поддержать пользователя при неясной причине грусти",
                rationale="можно продолжить без нового intake-вопроса",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    async def fake_extract_expert_card(state):
        return (
            EmotionalExpertCard(
                support="Я рядом.",
                step_now="Расскажи, как эта грусть ощущается для тебя сейчас.",
                follow_up="нет",
                needs_more_info=BinaryChoice.NO,
                rationale="эксперт может мягко продолжить без уточнения причины",
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
            message_type="short_answer",
            model_tier="lite",
        )
    )

    assert state.intake_card is not None
    assert state.intake_card.problem == "чувствуется грусть"
    assert state.intake_card.context == "причина пользователю не известна"
    assert state.intake_card.needs_clarification is BinaryChoice.NO
    assert state.intake_card.question == "нет"
    assert state.intake_card.ready_to_delegate is BinaryChoice.YES
    assert state.execution_kind is ExecutionKind.DELEGATE
    assert state.diagnostics["intake"]["llm"]["normalized_unknown_reason"] is True


@pytest.mark.asyncio
async def test_first_module_keeps_specific_reason_even_with_unknown_words(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            IntakeCard(
                problem="грусть после диализа",
                context="после диализа становится тяжелее эмоционально",
                needs_clarification=BinaryChoice.NO,
                question="нет",
                ready_to_delegate=BinaryChoice.YES,
                rationale="конкретный триггер уже есть",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    async def fake_extract_delegation_card(state):
        return (
            DelegationCard(
                expert=DelegationExpert.EMOTIONAL_SUPPORT,
                task="поддержать пользователя при грусти после диализа",
                rationale="причина уже обозначена",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    async def fake_extract_expert_card(state):
        return (
            EmotionalExpertCard(
                support="Я рядом.",
                step_now="Давай разберем, что именно тяжелее всего после диализа.",
                follow_up="нет",
                needs_more_info=BinaryChoice.NO,
                rationale="можно продолжать от конкретного триггера",
            ),
            {"final_status": "success", "succeeded_on_attempt": 1},
        )

    monkeypatch.setattr(graph_engine, "_COMPILED_GRAPH", False)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_delegation_card", fake_extract_delegation_card)
    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_emotional_expert_card", fake_extract_expert_card)

    state = await run_first_module(
        FirstModuleInput(
            user_message="не знаю, может после диализа меня накрывает",
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

    assert state.intake_card is not None
    assert state.intake_card.problem == "грусть после диализа"
    assert "причина пользователю не известна" not in state.intake_card.context
    assert state.diagnostics["intake"]["llm"].get("normalized_unknown_reason") is None
    assert state.execution_kind is ExecutionKind.DELEGATE
