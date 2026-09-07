"""Unit-тесты для защиты от повторной отметки приёма в один слот за день.

Баг: `check_duplicate_intake` ловит только приёмы в пределах ±5 минут, поэтому
утреннюю дозу можно было отметить принятой много раз за день. Теперь
`find_slot_duplicate` блокирует приём, если для слота уже отмечено столько же
приёмов, сколько предусмотрено расписанием.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.medications.service import find_slot_duplicate

DAY = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)


def _prescription(schedule):
    return SimpleNamespace(id=1, medication_name="Аспирин", intake_schedule=schedule)


def _intake(slot, dt):
    return SimpleNamespace(intake_slot=slot, intake_datetime=dt)


def test_no_intakes_no_duplicate():
    p = _prescription(["morning"])
    assert find_slot_duplicate(p, [], intake_slot="morning", intake_datetime=DAY) is None


def test_second_morning_same_day_is_duplicate():
    p = _prescription(["morning"])
    existing = [_intake("morning", DAY.replace(hour=7))]
    dup = find_slot_duplicate(p, existing, intake_slot="morning", intake_datetime=DAY)
    assert dup is existing[0]


def test_same_slot_next_day_is_allowed():
    p = _prescription(["morning"])
    existing = [_intake("morning", DAY - timedelta(days=1))]
    assert find_slot_duplicate(p, existing, intake_slot="morning", intake_datetime=DAY) is None


def test_other_slot_not_blocked():
    p = _prescription(["morning", "evening"])
    existing = [_intake("morning", DAY)]
    assert find_slot_duplicate(p, existing, intake_slot="evening", intake_datetime=DAY) is None


def test_schedule_with_repeated_slot_allows_that_many():
    # 4×/день: morning, morning, afternoon, evening → две утренние дозы законны
    p = _prescription(["morning", "morning", "afternoon", "evening"])
    one = [_intake("morning", DAY.replace(hour=7))]
    assert find_slot_duplicate(p, one, intake_slot="morning", intake_datetime=DAY) is None

    two = one + [_intake("morning", DAY.replace(hour=9))]
    dup = find_slot_duplicate(p, two, intake_slot="morning", intake_datetime=DAY)
    assert dup is two[-1]  # самый поздний из уже отмеченных


def test_no_slot_never_flagged_here():
    p = _prescription(["morning"])
    existing = [_intake(None, DAY)]
    assert find_slot_duplicate(p, existing, intake_slot=None, intake_datetime=DAY) is None


def test_returns_latest_duplicate():
    p = _prescription(["morning"])
    early = _intake("morning", DAY.replace(hour=6))
    late = _intake("morning", DAY.replace(hour=9))
    dup = find_slot_duplicate(p, [early, late], intake_slot="morning", intake_datetime=DAY)
    assert dup is late
