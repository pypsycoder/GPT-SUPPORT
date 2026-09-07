"""Unit-тесты для app.dialysis.service.get_dialysis_window (мок-сессия)."""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dialysis.service import DEFAULT_SHIFT_TIMES, get_dialysis_window

# Среда 2026-09-09 → isoweekday() == 3
WED = date(2026, 9, 9)


def _result(value):
    return MagicMock(scalar_one_or_none=MagicMock(return_value=value))


def _session(*execute_returns):
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_result(v) for v in execute_returns])
    return session


@pytest.mark.asyncio
async def test_no_schedule_returns_none():
    session = _session(None)
    assert await get_dialysis_window(session, patient_id=1, date=WED) is None


@pytest.mark.asyncio
async def test_non_dialysis_weekday_returns_none():
    schedule = SimpleNamespace(weekdays=[1, 5], shift="morning")  # нет среды
    session = _session(schedule)
    assert await get_dialysis_window(session, patient_id=1, date=WED) is None


@pytest.mark.asyncio
async def test_uses_center_shift_times():
    schedule = SimpleNamespace(weekdays=[3], shift="afternoon")
    center = SimpleNamespace(
        afternoon_start=time(13, 30),
        afternoon_end=time(17, 15),
    )
    session = _session(schedule, "center-uuid", center)

    window = await get_dialysis_window(session, patient_id=1, date=WED)

    assert window is not None
    assert window.shift == "afternoon"
    assert window.start == "13:30"
    assert window.end == "17:15"


@pytest.mark.asyncio
async def test_falls_back_to_defaults_when_no_center():
    schedule = SimpleNamespace(weekdays=[3], shift="evening")
    session = _session(schedule, None)  # center_id отсутствует

    window = await get_dialysis_window(session, patient_id=1, date=WED)

    d_start, d_end = DEFAULT_SHIFT_TIMES["evening"]
    assert window is not None
    assert window.start == d_start.strftime("%H:%M") == "18:00"
    assert window.end == d_end.strftime("%H:%M") == "21:00"


@pytest.mark.asyncio
async def test_falls_back_when_center_missing_times():
    schedule = SimpleNamespace(weekdays=[3], shift="morning")
    center = SimpleNamespace()  # нет morning_start/_end
    session = _session(schedule, "center-uuid", center)

    window = await get_dialysis_window(session, patient_id=1, date=WED)

    assert window is not None
    assert window.start == "08:00"
    assert window.end == "11:00"
