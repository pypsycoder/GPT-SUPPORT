import pytest

from app.llm.langgraph_supervisor.models import BinaryChoice, DelegationCard, DelegationExpert, FirstModuleState, IntakeCard
from app.llm.langgraph_supervisor.policy import (
    build_delegation_user_prompt,
    build_emotional_expert_system_prompt,
    build_emotional_expert_user_prompt,
    build_intake_system_prompt,
    extract_delegation_card,
    validate_emotional_expert_card,
)
from app.llm.langgraph_supervisor.models import EmotionalExpertCard
from app.llm.supervisor.models import CurrentState


def test_intake_prompt_delegates_unknown_reason_answers_without_more_clarification():
    prompt = build_intake_system_prompt()

    assert "не знаю" in prompt
    assert "просто ничего не радует" in prompt
    assert "причина пользователю не известна" in prompt
    assert "Нужно уточнение: нет" in prompt
    assert "Готово к передаче: да" in prompt


def test_expert_prompts_forbid_cause_search_when_reason_is_unknown():
    state = FirstModuleState(
        user_message="без понятия",
        current_state=CurrentState(),
        message_type="short_answer",
        model_tier="lite",
        intake_card=IntakeCard(
            problem="грусть",
            context="причина пользователю не известна",
            needs_clarification=BinaryChoice.NO,
            question="нет",
            ready_to_delegate=BinaryChoice.YES,
            rationale="переход к эксперту",
        ),
        delegation_card=DelegationCard(
            expert=DelegationExpert.EMOTIONAL_SUPPORT,
            task="поддержать пользователя",
            rationale="причина пока неизвестна",
        ),
    )

    system_prompt = build_emotional_expert_system_prompt()
    delegation_prompt = build_delegation_user_prompt(state)
    expert_prompt = build_emotional_expert_user_prompt(state)

    assert "Не формулируй задачу как поиск причины" in delegation_prompt
    assert "Не задавай вопрос о причине" in expert_prompt
    assert "не пытайся выяснить причину" in system_prompt


def test_validate_emotional_expert_card_rejects_question_in_step_now():
    card = EmotionalExpertCard(
        support="Я рядом.",
        step_now="Что именно вас беспокоит?",
        follow_up="нет",
        needs_more_info=BinaryChoice.NO,
        rationale="ошибка формата",
    )

    try:
        validate_emotional_expert_card(card)
    except ValueError as exc:
        assert "step_now" in str(exc)
    else:
        raise AssertionError("validate_emotional_expert_card must reject question-like step_now")


def test_delegation_prompt_mentions_local_education_grounding():
    state = FirstModuleState(
        user_message="объясни, что значит слабость после диализа",
        current_state=CurrentState(),
        message_type="full_message",
        model_tier="lite",
        intake_card=IntakeCard(
            problem="слабость после диализа",
            context="пользователь просит объяснение",
            needs_clarification=BinaryChoice.NO,
            question="нет",
            ready_to_delegate=BinaryChoice.YES,
            rationale="контекст собран",
        ),
        education_rag_grounding_items=[
            {
                "lesson_id": 7,
                "lesson_code": "07_post_dialysis_fatigue",
                "lesson_title": "Слабость после диализа",
                "chunk": "После процедуры слабость может ощущаться заметнее в день диализа.",
            }
        ],
    )

    prompt = build_delegation_user_prompt(state)

    assert "локальный educational grounding" in prompt.lower()
    assert "07_post_dialysis_fatigue" in prompt
    assert "Слабость после диализа" in prompt


@pytest.mark.asyncio
async def test_extract_delegation_card_rejects_education_without_grounding(monkeypatch):
    async def fake_call_structured_llm(**kwargs):
        return (
            "Эксперт: education\nЗадача: коротко объяснить тему\nОбоснование: нужен educational expert",
            "A1",
            10,
            5,
            20,
        )

    monkeypatch.setattr("app.llm.langgraph_supervisor.policy._MAX_ATTEMPTS", 1)
    monkeypatch.setattr("app.llm.langgraph_supervisor.policy._call_structured_llm", fake_call_structured_llm)

    state = FirstModuleState(
        user_message="объясни, что это значит",
        current_state=CurrentState(),
        message_type="full_message",
        model_tier="lite",
        intake_card=IntakeCard(
            problem="слабость после диализа",
            context="пользователь хочет понять состояние",
            needs_clarification=BinaryChoice.NO,
            question="нет",
            ready_to_delegate=BinaryChoice.YES,
            rationale="контекст собран",
        ),
    )

    card, diagnostics = await extract_delegation_card(state)

    assert card is None
    assert diagnostics["final_status"] == "failed_after_retries"
    assert diagnostics["failures"][0]["error_message"] == "education expert requires local educational grounding"
