"""Integration tests for vitals CRUD helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.users.models import User
from app.vitals import crud as vitals_crud
from app.vitals.models import VitalMeasurement


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
async def test_vitals_crud_flow(async_session, user):
    """End-to-end check for creating, reading and deleting vitals measurements."""

    now = datetime.utcnow()

    # Create three measurements with different timestamps so ordering can be verified.
    old_measurement = await vitals_crud.create_measurement(async_session, user.id, pulse=50)
    mid_measurement = await vitals_crud.create_measurement(async_session, user.id, pulse=60)
    latest_measurement = await vitals_crud.create_measurement(async_session, user.id, pulse=70)

    old_measurement.measured_at = now - timedelta(days=10)
    mid_measurement.measured_at = now - timedelta(days=3)
    latest_measurement.measured_at = now
    await async_session.flush()

    recent_measurements = await vitals_crud.get_user_measurements(async_session, user.id, days=7)
    recent_ids = [measurement.id for measurement in recent_measurements]
    assert recent_ids == [latest_measurement.id, mid_measurement.id], "measurements must be sorted by time desc"

    latest_from_db = await vitals_crud.get_latest_measurement(async_session, user.id)
    assert latest_from_db is not None
    assert latest_from_db.id == latest_measurement.id

    await vitals_crud.delete_measurement(async_session, mid_measurement.id)
    await async_session.flush()

    deleted = await async_session.get(VitalMeasurement, mid_measurement.id)
    assert deleted is None, "measurement should be removed from the database"


@pytest.mark.asyncio
async def test_create_measurement_requires_existing_user(async_session):
    """The FK constraint on vitals.measurements.user_id should reject unknown users."""

    with pytest.raises(IntegrityError):
        await vitals_crud.create_measurement(async_session, user_id=999999, pulse=90)

    # SQLAlchemy marks the transaction as failed after IntegrityError; roll it back for cleanliness.
    await async_session.rollback()
