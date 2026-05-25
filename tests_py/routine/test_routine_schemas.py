from __future__ import annotations

from datetime import date

from app.routine.schemas import DailyVerificationCreate


def test_daily_verification_accepts_diet_specific_done_value():
    payload = DailyVerificationCreate(
        verification_date=date(2026, 4, 4),
        template_executed={
            "diet": {
                "done": "fully",
                "actual_duration": None,
            }
        },
        day_control_score=7,
    )

    assert payload.template_executed is not None
    assert payload.template_executed["diet"].done == "fully"
