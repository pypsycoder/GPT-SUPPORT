from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm.morning_service import _build_weekly_summary, build_morning_message, get_daily_context_for_llm


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
