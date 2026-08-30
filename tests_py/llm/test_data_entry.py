"""Тесты записи показателей без обращения к модели."""

from __future__ import annotations

import pytest

from app.llm import router_l0
from app.llm.pipeline.stages.data_entry import DataEntryStage, build_reply
from app.llm.pipeline.types import LLMRequest, PipelineContext


def _ctx(text: str) -> PipelineContext:
    context = PipelineContext(request=LLMRequest(patient_id=1, user_input=text))
    context.l0 = router_l0.classify(text)
    return context


# --------------------------------------------------------------------------- #
# Текст ответа
# --------------------------------------------------------------------------- #

def test_normal_bp_gets_a_short_confirmation():
    reply = build_reply([{"type": "BP", "systolic": 125, "diastolic": 85}], None)

    assert reply == "Записал: давление 125/85. Это в пределах нормы."


def test_elevated_bp_is_named_without_diagnosing():
    reply = build_reply([{"type": "BP", "systolic": 150, "diastolic": 95}], "bp_high")

    assert "Записал: давление 150/95." in reply
    assert "Выше обычного." in reply
    # Комментарий по числам, а не медицинская оценка.
    assert "криз" not in reply.lower()


def test_critical_bp_uses_the_fixed_template():
    """На кризисных цифрах текст фиксированный: разночтения тут опаснее сухости."""
    reply = build_reply([{"type": "BP", "systolic": 200, "diastolic": 100}], "bp_critical")

    assert "200/100" in reply
    assert "перемерь" in reply
    assert "диализн" in reply
    # Это не психологический кризис — телефона доверия здесь быть не должно.
    assert "8-800" not in reply


def test_several_vitals_in_one_message():
    reply = build_reply(
        [{"type": "BP", "systolic": 120, "diastolic": 80}, {"type": "PULSE", "value": 71}], None
    )

    assert "давление 120/80" in reply
    assert "пульс 71" in reply


def test_units_are_rendered():
    assert "1200 мл" in build_reply([{"type": "WATER", "value": 1200}], None)
    assert "70.5 кг" in build_reply([{"type": "WEIGHT", "value": 70.5}], None)


# --------------------------------------------------------------------------- #
# Стадия
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_stage_short_circuits_on_a_reading():
    context = await DataEntryStage().process(_ctx("давление 125 на 85"))

    assert context.early_response_source == "data_entry"
    assert context.pending_vitals == [{"type": "BP", "systolic": 125, "diastolic": 85}]
    assert context.diagnostics["data_entry"]["triggered"] is True


@pytest.mark.asyncio
async def test_stage_is_silent_when_l0_parsed_nothing():
    context = PipelineContext(request=LLMRequest(patient_id=1, user_input="давление 125 на 85"))
    context.l0 = None

    context = await DataEntryStage().process(context)

    assert context.early_response is None
    assert context.pending_vitals == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "Если давление 129 на 89 это норма?",   # вопрос, а не запись
        "какое мое давление",                    # чтение, а не запись
        "мне тревожно перед диализом",           # вообще не про показатели
        "Давление",                              # нечего записывать
    ],
)
async def test_stage_does_not_intercept_non_entries(text):
    context = await DataEntryStage().process(_ctx(text))

    assert context.early_response is None
    assert context.pending_vitals == []


@pytest.mark.asyncio
async def test_critical_bp_still_short_circuits():
    """Высокое давление — запись с шаблоном, а не повод звать модель."""
    context = await DataEntryStage().process(_ctx("У меня давление 200 на 100"))

    assert context.early_response_source == "data_entry"
    assert "перемерь" in context.early_response
    assert context.diagnostics["data_entry"]["alert"] == "bp_critical"


# --------------------------------------------------------------------------- #
# Что умеет писать vitals_writer
# --------------------------------------------------------------------------- #

def test_sleep_is_not_written_as_a_vital():
    """Схема сна требует отход ко сну и пробуждение — из одной цифры её не собрать."""
    from app.llm import vitals_writer

    assert "SLEEP" not in vitals_writer._WRITERS
    assert vitals_writer._prepare(1, {"type": "SLEEP", "value": 3.0}) is None


@pytest.mark.asyncio
async def test_sleep_report_gets_a_tracker_button_not_a_false_confirmation():
    """«Спал 3 часа» → короткая реплика + кнопка в трекер сна, без «Записал»."""
    context = await DataEntryStage().process(_ctx("я спал 3 часа сегодня"))

    assert context.early_response_source == "sleep_entry"
    assert "Записал" not in context.early_response
    assert context.pending_vitals == []
    assert context.early_response_buttons == [
        {"label": "Внести данные о сне", "action": "open_sleep"}
    ]


@pytest.mark.asyncio
async def test_sleep_with_distress_is_left_to_the_model():
    context = await DataEntryStage().process(_ctx("поспал 4 часа, сил совсем нет"))

    assert context.early_response is None
    assert context.early_response_buttons is None


@pytest.mark.asyncio
async def test_routine_report_gets_a_tracker_button():
    context = await DataEntryStage().process(_ctx("сегодня соблюдал распорядок дня"))

    assert context.early_response_source == "routine_entry"
    assert context.pending_vitals == []
    assert context.early_response_buttons == [
        {"label": "Открыть распорядок дня", "action": "open_schedule"}
    ]


def test_prepare_builds_schemas_for_supported_types():
    from app.llm import vitals_writer

    bp = vitals_writer._prepare(1, {"type": "BP", "systolic": 120, "diastolic": 80})
    assert (bp.systolic, bp.diastolic) == (120, 80)
    assert vitals_writer._prepare(1, {"type": "PULSE", "value": 71}).bpm == 71
    assert float(vitals_writer._prepare(1, {"type": "WEIGHT", "value": 70.5}).weight) == 70.5
    assert vitals_writer._prepare(1, {"type": "WATER", "value": 1200}).volume_ml == 1200


def test_prepare_ignores_unknown_type():
    from app.llm import vitals_writer

    assert vitals_writer._prepare(1, {"type": "TEMPERATURE", "value": 37}) is None


# --------------------------------------------------------------------------- #
# Показатели вместе с переживанием
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_reading_with_emotion_is_not_answered_by_template():
    """«Давление 200 на 100, мне очень страшно» — сухой шаблон тут неуместен."""
    context = await DataEntryStage().process(_ctx("давление 200 на 100, мне очень страшно"))

    assert context.early_response is None
    assert context.diagnostics["data_entry"]["reason"] == "vitals_with_emotion"


@pytest.mark.asyncio
async def test_reading_with_emotion_is_still_recorded():
    """Отвечает модель, но цифры терять нельзя."""
    context = await DataEntryStage().process(_ctx("давление 200 на 100, мне очень страшно"))

    assert context.pending_vitals == [{"type": "BP", "systolic": 200, "diastolic": 100}]
    assert context.diagnostics["data_entry"]["recorded_anyway"] is True


@pytest.mark.asyncio
async def test_question_about_numbers_is_not_recorded():
    """Человек спрашивает, а не отчитывается — записывать нечего."""
    context = await DataEntryStage().process(_ctx("Если давление 129 на 89 это норма?"))

    assert context.early_response is None
    assert context.pending_vitals == []


def test_l0_separates_a_bare_reading_from_one_with_feelings():
    plain = router_l0.classify("давление 200 на 100")
    with_emotion = router_l0.classify("давление 200 на 100, мне очень страшно")

    assert plain.intent == "data_entry"
    assert with_emotion.intent is None
    assert with_emotion.rule == "vitals_with_emotion"
    # Цифры и тревога разобраны в обоих случаях.
    assert plain.vitals == with_emotion.vitals
    assert plain.alert == with_emotion.alert == "bp_critical"
