"""Тесты времени старта активностей в модуле d230 (планер + верификация)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.routine.schemas import (
    ActivityExecution,
    ActivityPlan,
    CustomPlannedActivity,
    DailyPlanCreate,
    DailyVerificationCreate,
)
from app.routine.service import RoutineService


# --- Схемы: валидация ЧЧ:ММ ---


@pytest.mark.parametrize("good", ["00:00", "08:05", "13:30", "23:59"])
def test_planned_start_accepts_valid_hhmm(good):
    assert ActivityPlan(planned=True, planned_start=good).planned_start == good


@pytest.mark.parametrize("bad", ["24:00", "8:5", "08:60", "morning", "08-00"])
def test_planned_start_rejects_bad(bad):
    with pytest.raises(ValidationError):
        ActivityPlan(planned=True, planned_start=bad)


def test_empty_string_normalises_to_none():
    assert ActivityPlan(planned=True, planned_start="").planned_start is None
    assert ActivityExecution(done="yes", actual_start="").actual_start is None


def test_plan_roundtrips_planned_start_through_create_schema():
    payload = DailyPlanCreate(
        plan_date=date(2026, 9, 9),
        template_activities={"physical": {"planned": True, "planned_duration": "1h", "planned_start": "08:00"}},
        custom_activities=[{"text": "Позвонить", "planned_duration": "15min", "planned_start": "10:30"}],
    )
    assert payload.template_activities["physical"].planned_start == "08:00"
    assert payload.custom_activities[0].planned_start == "10:30"


def test_verification_roundtrips_actual_start():
    payload = DailyVerificationCreate(
        verification_date=date(2026, 9, 9),
        template_executed={"physical": {"done": "yes", "actual_start": "08:20"}},
        day_control_score=6,
    )
    assert payload.template_executed["physical"].actual_start == "08:20"


def test_custom_planned_activity_time_optional():
    assert CustomPlannedActivity(text="x").planned_start is None


# --- Метрика schedule_adherence_rate ---


def _plan(**kw):
    base = dict(
        template_activities={},
        added_from_pool={},
        custom_activities=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _ver(**kw):
    base = dict(
        template_executed={},
        pool_added_executed={},
        custom_executed={},
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_adherence_none_when_no_pairs():
    assert RoutineService._compute_schedule_adherence_rate(_plan(), _ver()) is None


def test_adherence_counts_within_tolerance():
    plan = _plan(
        template_activities={
            "physical": {"planned": True, "planned_start": "08:00"},
            "work": {"planned": True, "planned_start": "12:00"},
        }
    )
    ver = _ver(
        template_executed={
            "physical": {"done": "yes", "actual_start": "08:25"},   # +25 → попал
            "work": {"done": "yes", "actual_start": "13:10"},        # +70 → не попал
        }
    )
    assert RoutineService._compute_schedule_adherence_rate(plan, ver) == 50.0


def test_adherence_ignores_not_done_activities():
    plan = _plan(template_activities={"physical": {"planned": True, "planned_start": "08:00"}})
    ver = _ver(template_executed={"physical": {"done": "no", "actual_start": "08:00"}})
    assert RoutineService._compute_schedule_adherence_rate(plan, ver) is None


def test_adherence_matches_custom_by_text():
    plan = _plan(custom_activities=[{"text": "Прогулка", "planned_start": "07:00"}])
    ver = _ver(custom_executed={"Прогулка": {"done": "yes", "actual_start": "07:05"}})
    assert RoutineService._compute_schedule_adherence_rate(plan, ver) == 100.0


@pytest.mark.parametrize(
    "value,expected",
    [
        ("08:00", 480),
        ("00:00", 0),
        ("23:59", 1439),
        ("8:00", 480),      # helper терпим к 1-значному часу (в БД так не хранится)
        ("25:00", None),    # вне диапазона
        ("08:70", None),
        (None, None),
        ("bad", None),
        ("08:00:00", None),
    ],
)
def test_hhmm_to_minutes(value, expected):
    assert RoutineService._hhmm_to_minutes(value) == expected
