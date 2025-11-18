"""CRUD operations for vital measurements."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.vitals.models import BpMeasurement, FluidIntakeEvent, WeightMeasurement


# 🩺 Создание записи артериального давления
async def create_bp_measurement(
    session: AsyncSession,
    user_id: int,
    systolic_mm_hg: int,
    diastolic_mm_hg: int,
    pulse_bpm: int | None,
    measured_at: datetime,
    context: str | None = None,
) -> BpMeasurement:
    measurement = BpMeasurement(
        user_id=user_id,
        systolic_mm_hg=systolic_mm_hg,
        diastolic_mm_hg=diastolic_mm_hg,
        pulse_bpm=pulse_bpm,
        measured_at=measured_at,
        context=context,
    )
    session.add(measurement)
    await session.flush()
    return measurement


# 💧 Событие приёма жидкости
async def create_fluid_intake_event(
    session: AsyncSession,
    user_id: int,
    volume_ml: int,
    intake_type: str | None,
    recorded_at: datetime,
) -> FluidIntakeEvent:
    intake_event = FluidIntakeEvent(
        user_id=user_id,
        volume_ml=volume_ml,
        intake_type=intake_type,
        recorded_at=recorded_at,
    )
    session.add(intake_event)
    await session.flush()
    return intake_event


# ⚖️ Измерение массы тела
async def create_weight_measurement(
    session: AsyncSession,
    user_id: int,
    weight_kg: Decimal | float,
    measured_at: datetime,
    context: str | None = None,
) -> WeightMeasurement:
    weight_measurement = WeightMeasurement(
        user_id=user_id,
        weight_kg=weight_kg,
        measured_at=measured_at,
        context=context,
    )
    session.add(weight_measurement)
    await session.flush()
    return weight_measurement


# 📈 Суточная сумма приёма жидкости
async def get_daily_fluid_total(
    session: AsyncSession, user_id: int, for_date: date
) -> int:
    start = datetime.combine(for_date, datetime.min.time())
    end = start + timedelta(days=1)

    stmt = (
        select(func.coalesce(func.sum(FluidIntakeEvent.volume_ml), 0))
        .where(
            FluidIntakeEvent.user_id == user_id,
            FluidIntakeEvent.recorded_at >= start,
            FluidIntakeEvent.recorded_at < end,
        )
    )
    result = await session.execute(stmt)
    total = result.scalar_one()
    return int(total)


# 🗑 Удаление записей (для тестов/отладки)
async def delete_bp_measurement(session: AsyncSession, measurement_id: int) -> None:
    stmt = delete(BpMeasurement).where(BpMeasurement.id == measurement_id)
    await session.execute(stmt)
    await session.flush()


async def delete_fluid_intake_event(session: AsyncSession, event_id: int) -> None:
    stmt = delete(FluidIntakeEvent).where(FluidIntakeEvent.id == event_id)
    await session.execute(stmt)
    await session.flush()


async def delete_weight_measurement(session: AsyncSession, measurement_id: int) -> None:
    stmt = delete(WeightMeasurement).where(WeightMeasurement.id == measurement_id)
    await session.execute(stmt)
    await session.flush()
