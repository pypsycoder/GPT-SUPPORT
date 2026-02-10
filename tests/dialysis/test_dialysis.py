# Tests for dialysis module: is_dialysis_day and API auth.

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.dialysis.service import is_dialysis_day


# --- is_dialysis_day (with mock session) ---


@pytest.mark.asyncio
async def test_is_dialysis_day_no_schedule_returns_none():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    result = await is_dialysis_day(session, patient_id=1, date=date(2025, 3, 3))
    assert result is None


@pytest.mark.asyncio
async def test_is_dialysis_day_weekday_in_schedule_returns_true():
    session = AsyncMock()
    mock_schedule = MagicMock()
    mock_schedule.weekdays = [1, 3, 5]
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_schedule))
    )
    # Monday 2025-03-03 is weekday 1
    result = await is_dialysis_day(session, patient_id=1, date=date(2025, 3, 3))
    assert result is True


@pytest.mark.asyncio
async def test_is_dialysis_day_weekday_not_in_schedule_returns_false():
    session = AsyncMock()
    mock_schedule = MagicMock()
    mock_schedule.weekdays = [1, 3, 5]
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_schedule))
    )
    # Sunday 2025-03-09 is weekday 7
    result = await is_dialysis_day(session, patient_id=1, date=date(2025, 3, 9))
    assert result is False


# --- API: endpoints require researcher auth (401 without cookie) ---


def test_centers_list_requires_auth():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/centers")
    assert resp.status_code == 401


def test_centers_create_requires_auth():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/centers",
        json={"name": "Test", "city": "Moscow", "timezone": "Europe/Moscow"},
    )
    assert resp.status_code == 401


def test_patient_schedules_list_requires_auth():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/patients/1/schedules")
    assert resp.status_code == 401


def test_import_schedules_requires_auth():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/import/schedules",
        files={"file": ("test.csv", b"patient_id,center_name,weekdays,shift,valid_from,change_reason\n")},
    )
    assert resp.status_code == 401
