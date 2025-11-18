"""Integration tests for vitals CRUD helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.users.models import User
from app.vitals import crud as vitals_crud
from app.vitals.models import (
    BpMeasurement,
    FluidIntakeEvent,
    WeightMeasurement,
)


@pytest.fixture
async def user(async_session):
    """Create a user record that other fixtures/tests can rely on."""

    new_user = User(
        full_name="Test User",
        telegram_id=f"test-{uuid.uuid4().hex}",
    )
    async_session.add(new_user)
    await async_session.flush()
    await async_session.refresh(new_user)
    return new_user


@pytest.mark.asyncio
async def test_bp_measurement_crud(async_session, user):
    """Create, fetch and delete blood pressure measurements."""

    now = datetime.utcnow()

    first = await vitals_crud.create_bp_measurement(
        async_session,
        user.id,
        systolic_mm_hg=120,
        diastolic_mm_hg=80,
        pulse_bpm=70,
        measured_at=now - timedelta(hours=2),
        context="home",
    )
    second = await vitals_crud.create_bp_measurement(
        async_session,
        user.id,
        systolic_mm_hg=130,
        diastolic_mm_hg=85,
        pulse_bpm=72,
        measured_at=now,
    )

    # Flush timestamps and ensure ordering by measured_at desc.
    await async_session.flush()

    stmt = (
        select(BpMeasurement)
        .where(BpMeasurement.user_id == user.id)
        .order_by(BpMeasurement.measured_at.desc())
    )
    result = await async_session.execute(stmt)
    measurements = result.scalars().all()

    assert [m.id for m in measurements] == [second.id, first.id]

    await vitals_crud.delete_bp_measurement(async_session, first.id)
    await async_session.flush()
    assert await async_session.get(BpMeasurement, first.id) is None


@pytest.mark.asyncio
async def test_fluid_intake_event_crud(async_session, user):
    """Create fluid intake events and aggregate by day."""

    today = datetime.utcnow()
    await vitals_crud.create_fluid_intake_event(
        async_session,
        user.id,
        volume_ml=250,
        intake_type="water",
        recorded_at=today - timedelta(hours=1),
    )
    await vitals_crud.create_fluid_intake_event(
        async_session,
        user.id,
        volume_ml=150,
        intake_type="tea",
        recorded_at=today,
    )

    total = await vitals_crud.get_daily_fluid_total(async_session, user.id, date.today())
    assert total == 400

    events = await async_session.execute(select(FluidIntakeEvent))
    for event in events.scalars():
        await vitals_crud.delete_fluid_intake_event(async_session, event.id)
    await async_session.flush()


@pytest.mark.asyncio
async def test_weight_measurement_crud(async_session, user):
    """Create and clean up weight measurements."""

    measurement = await vitals_crud.create_weight_measurement(
        async_session,
        user.id,
        weight_kg=70.5,
        measured_at=datetime.utcnow(),
        context="pre_hd",
    )
    await async_session.flush()

    fetched = await async_session.get(WeightMeasurement, measurement.id)
    assert fetched is not None
    assert float(fetched.weight_kg) == 70.5

    await vitals_crud.delete_weight_measurement(async_session, measurement.id)
    await async_session.flush()
    assert await async_session.get(WeightMeasurement, measurement.id) is None


@pytest.mark.asyncio
async def test_bp_measurement_requires_existing_user(async_session):
    """The FK constraint on vitals.bp_measurement.user_id should reject unknown users."""

    with pytest.raises(IntegrityError):
        await vitals_crud.create_bp_measurement(
            async_session,
            user_id=999999,
            systolic_mm_hg=120,
            diastolic_mm_hg=80,
            pulse_bpm=None,
            measured_at=datetime.utcnow(),
        )

    await async_session.rollback()
