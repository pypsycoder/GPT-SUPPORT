# ============================================
# Dialysis CRUD: Центры и расписания
# ============================================

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dialysis.models import Center, DialysisSchedule


async def list_centers(session: AsyncSession) -> Sequence[Center]:
    result = await session.execute(select(Center).order_by(Center.name))
    return result.scalars().all()


async def get_center_by_id(session: AsyncSession, center_id: UUID) -> Center | None:
    result = await session.execute(select(Center).where(Center.id == center_id))
    return result.scalar_one_or_none()


async def create_center(
    session: AsyncSession,
    *,
    name: str,
    city: str | None = None,
    timezone: str = "Europe/Moscow",
) -> Center:
    center = Center(name=name, city=city, timezone=timezone)
    session.add(center)
    await session.commit()
    await session.refresh(center)
    return center


async def get_active_schedule(session: AsyncSession, patient_id: int) -> DialysisSchedule | None:
    result = await session.execute(
        select(DialysisSchedule)
        .where(DialysisSchedule.patient_id == patient_id)
        .where(DialysisSchedule.valid_to.is_(None))
    )
    return result.scalar_one_or_none()


async def list_schedules_for_patient(
    session: AsyncSession,
    patient_id: int,
) -> Sequence[DialysisSchedule]:
    result = await session.execute(
        select(DialysisSchedule)
        .where(DialysisSchedule.patient_id == patient_id)
        .order_by(DialysisSchedule.valid_from.desc())
    )
    return result.scalars().all()


async def get_schedule_by_id(session: AsyncSession, schedule_id: UUID) -> DialysisSchedule | None:
    result = await session.execute(select(DialysisSchedule).where(DialysisSchedule.id == schedule_id))
    return result.scalar_one_or_none()


async def create_schedule(
    session: AsyncSession,
    *,
    patient_id: int,
    weekdays: list[int],
    shift: str,
    valid_from: date,
    created_by: int,
    change_reason: str | None = None,
) -> DialysisSchedule:
    s = DialysisSchedule(
        patient_id=patient_id,
        weekdays=weekdays,
        shift=shift,
        valid_from=valid_from,
        valid_to=None,
        created_by=created_by,
        change_reason=change_reason,
    )
    session.add(s)
    await session.flush()
    await session.refresh(s)
    return s


async def close_schedule(
    session: AsyncSession,
    schedule: DialysisSchedule,
    *,
    valid_to: date,
    closed_by: int,
    change_reason: str | None = None,
) -> None:
    schedule.valid_to = valid_to
    schedule.closed_at = datetime.now(timezone.utc)
    schedule.closed_by = closed_by
    if change_reason is not None:
        schedule.change_reason = change_reason
    await session.flush()
