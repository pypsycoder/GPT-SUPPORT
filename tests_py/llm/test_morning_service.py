from __future__ import annotations

import pytest

from app.llm.morning_service import (
    _build_achievement_lines,
    _build_weekly_summary,
    build_morning_message,
    get_daily_context_for_llm,
)


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


class FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, *args, **kwargs):
        return FakeResult(self._row)


async def test_build_weekly_summary_detects_sleep_focus():
    summary = _build_weekly_summary(
        {
            "recent_sleep_days_logged": 2,
            "recent_active_medications": 1,
            "recent_medication_days_logged": 6,
            "recent_bp_days_logged": 4,
        }
    )

    assert summary["focus_topic"] == "sleep"
    assert "сон отмечался нерегулярно" in summary["summary_lines"][0]
    assert summary["cta_text"] == "Хотите посмотреть короткий материал про сон?"


async def test_build_morning_message_appends_weekly_summary_and_cta():
    message = build_morning_message(
        {
            "time_of_day": "morning",
            "dialysis_today": False,
            "morning_meds_total": 0,
            "morning_meds_done": 0,
            "morning_meds_pending": 0,
            "missed_yesterday": [],
            "streak_medications": 0,
            "streak_best": 0,
            "summary_lines": [
                "В последнее время сон отмечался нерегулярно.",
                "Лекарства в последние дни отмечались не каждый день.",
            ],
            "focus_topic": "sleep",
            "cta_text": "Хотите посмотреть короткий материал про сон?",
        }
    )

    assert "В последнее время сон отмечался нерегулярно." in message["text"]
    assert "Лекарства в последние дни отмечались не каждый день." in message["text"]
    assert "Хотите посмотреть короткий материал про сон?" in message["text"]
    assert any(button["action"] == "open_sleep_lesson" for button in message["buttons"])


async def test_achievement_lines_from_lessons_and_practices():
    lines = _build_achievement_lines(
        {"recent_lessons_completed": 2, "recent_practices_completed": 1}
    )
    assert lines == ["прошли 2 занятия", "выполнили 1 практику"]


async def test_achievement_lines_capped_at_two():
    lines = _build_achievement_lines(
        {
            "recent_lessons_completed": 3,
            "recent_practices_completed": 4,
            "recent_sleep_days_logged": 6,
            "recent_active_medications": 2,
            "recent_medication_days_logged": 7,
        }
    )
    assert len(lines) == 2


async def test_achievement_lines_skip_streak_when_digest_has_its_own_block():
    # нет пропусков → build_morning_message покажет отдельный блок про серию
    assert _build_achievement_lines({"streak_medications": 9, "missed_yesterday": []}) == []
    # есть пропуск → своего блока не будет, серию можно упомянуть
    assert _build_achievement_lines(
        {"streak_medications": 9, "missed_yesterday": ["сон"]}
    ) == ["серия по лекарствам — 9 дней"]


async def test_weekly_summary_builds_achievement_summary():
    result = _build_weekly_summary(
        {"recent_lessons_completed": 2, "recent_sleep_days_logged": 6}
    )
    assert result["achievement_summary"] == (
        "На этой неделе вы прошли 2 занятия и почти каждый день отмечали сон — здорово."
    )


async def test_cold_start_message_is_a_welcome_not_a_scolding():
    message = build_morning_message(
        {
            "time_of_day": "morning",
            "has_history": False,
            # даже если контекст насчитал «пропуски» — при пустой БД их не показываем
            "dialysis_today": False,
            "morning_meds_pending": 0,
            "missed_yesterday": ["сон", "показатели"],
            "streak_medications": 0,
            "streak_best": 0,
            "summary_lines": ["В последнее время сон отмечался нерегулярно."],
            "achievement_summary": "",
        }
    )
    assert "нерегулярно" not in message["text"]
    assert "не было записей" not in message["text"]
    assert "Доброе утро." in message["text"]
    assert any(b["action"] == "open_trackers" for b in message["buttons"])


async def test_morning_message_puts_achievements_before_problems():
    message = build_morning_message(
        {
            "time_of_day": "morning",
            "dialysis_today": False,
            "morning_meds_pending": 0,
            "morning_meds_total": 0,
            "morning_meds_done": 0,
            "missed_yesterday": [],
            "streak_medications": 0,
            "streak_best": 0,
            "summary_lines": ["В последнее время сон отмечался нерегулярно."],
            "achievement_summary": "На этой неделе вы прошли 2 занятия — здорово.",
            "focus_topic": "sleep",
            "cta_text": "Хотите посмотреть короткий материал про сон?",
        }
    )
    text = message["text"]
    assert text.index("прошли 2 занятия") < text.index("сон отмечался нерегулярно")


async def test_get_daily_context_for_llm_uses_summary_lines_and_cta():
    session = FakeSession(
        (
            {
                "dialysis_today": True,
                "morning_meds_pending": 1,
                "missed_yesterday": ["сон"],
                "summary_lines": [
                    "В последнее время сон отмечался нерегулярно.",
                    "Лекарства в последние дни отмечались не каждый день.",
                ],
                "streak_medications": 4,
                "cta_text": "Хотите посмотреть короткий материал про сон?",
            },
        )
    )

    daily_context = await get_daily_context_for_llm(patient_id=1, session=session)

    assert "сегодня день диализа" in daily_context
    assert "утренние лекарства не отмечены" in daily_context
    assert "В последнее время сон отмечался нерегулярно." in daily_context
    assert "мягкий фокус: Хотите посмотреть короткий материал про сон?" in daily_context


async def test_get_daily_context_for_llm_surfaces_achievements():
    session = FakeSession(
        (
            {
                "dialysis_today": False,
                "morning_meds_pending": 0,
                "missed_yesterday": [],
                "achievement_lines": ["прошли 2 занятия", "выполнили 1 практику"],
            },
        )
    )

    daily_context = await get_daily_context_for_llm(patient_id=1, session=session)

    assert "за неделю: прошли 2 занятия, выполнили 1 практику" in daily_context
