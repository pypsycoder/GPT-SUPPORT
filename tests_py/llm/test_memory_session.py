from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.llm.memory import InMemorySTMemoryStore, merge_st_memory


pytestmark = [pytest.mark.unit]


def test_merge_st_memory_replaces_by_key() -> None:
    existing = [
        {
            "key": "current_problem",
            "value": "anxiety",
            "status": "active",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }
    ]
    updates = [
        {
            "key": "current_problem",
            "value": "low_energy_today",
            "status": "active",
            "expires_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        }
    ]

    merged = merge_st_memory(existing, updates)

    assert len(merged) == 1
    assert merged[0]["value"] == "low_energy_today"


def test_merge_st_memory_drops_expired_entries() -> None:
    now = datetime.now(UTC)
    existing = [
        {
            "key": "current_problem",
            "value": "anxiety",
            "status": "active",
            "expires_at": (now - timedelta(minutes=1)).isoformat(),
        }
    ]

    merged = merge_st_memory(existing, [], now=now)

    assert merged == []


def test_in_memory_store_round_trip() -> None:
    store = InMemorySTMemoryStore()
    result = store.write(
        patient_id=1,
        session_id="sess_1",
        thread_id="main",
        updates=[
            {
                "key": "current_intent",
                "value": "practical_day_support",
                "status": "active",
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            }
        ],
    )

    assert len(result) == 1
    read_back = store.read(patient_id=1, session_id="sess_1", thread_id="main")
    assert read_back[0]["key"] == "current_intent"
    assert read_back[0]["value"] == "practical_day_support"


def test_in_memory_store_isolated_by_session_and_thread() -> None:
    store = InMemorySTMemoryStore()
    store.write(
        patient_id=1,
        session_id="sess_a",
        thread_id="main",
        updates=[
            {
                "key": "current_problem",
                "value": "sleep",
                "status": "active",
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            }
        ],
    )

    assert store.read(patient_id=1, session_id="sess_b", thread_id="main") == []
    assert store.read(patient_id=1, session_id="sess_a", thread_id="other") == []
    assert store.read(patient_id=1, session_id="sess_a", thread_id="main")[0]["value"] == "sleep"
