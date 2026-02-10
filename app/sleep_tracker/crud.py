# ============================================
# Sleep Tracker CRUD: создание, чтение по дате, обновление, список
# ============================================

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.sleep_tracker.models import SleepRecord


async def create(
    session: AsyncSession,
    data: dict,
) -> SleepRecord:
    record = SleepRecord(**data)
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def get_by_id(
    session: AsyncSession,
    record_id: UUID,
) -> Optional[SleepRecord]:
    stmt = select(SleepRecord).where(SleepRecord.id == record_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_patient_and_date(
    session: AsyncSession,
    patient_id: int,
    sleep_date: date,
) -> Optional[SleepRecord]:
    stmt = (
        select(SleepRecord)
        .where(SleepRecord.patient_id == patient_id)
        .where(SleepRecord.sleep_date == sleep_date)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_record(
    session: AsyncSession,
    record_id: UUID,
    patient_id: int,
    update_data: dict,
) -> Optional[SleepRecord]:
    """Обновить запись, установить updated_at = now(), edit_count += 1."""
    from sqlalchemy import func

    stmt = (
        update(SleepRecord)
        .where(SleepRecord.id == record_id)
        .where(SleepRecord.patient_id == patient_id)
        .values(
            updated_at=func.now(),
            edit_count=SleepRecord.edit_count + 1,
            **update_data,
        )
    )
    result = await session.execute(stmt)
    if result.rowcount == 0:
        return None
    return await get_by_id(session, record_id)


async def list_by_patient(
    session: AsyncSession,
    patient_id: int,
    limit: int = 100,
    offset: int = 0,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Sequence[SleepRecord]:
    stmt = select(SleepRecord).where(SleepRecord.patient_id == patient_id)
    if date_from is not None:
        stmt = stmt.where(SleepRecord.submitted_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(SleepRecord.submitted_at <= date_to)
    stmt = stmt.order_by(SleepRecord.sleep_date.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()
