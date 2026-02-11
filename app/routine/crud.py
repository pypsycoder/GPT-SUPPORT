from __future__ import annotations

"""CRUD-helpers для модуля рутины (d230)."""

from datetime import date
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.routine.models import BaselineRoutine, DailyPlan, DailyVerification


# --- BaselineRoutine ---


async def get_active_baseline(session: AsyncSession, patient_id: int) -> Optional[BaselineRoutine]:
    stmt = (
        select(BaselineRoutine)
        .where(BaselineRoutine.patient_id == patient_id)
        .where(BaselineRoutine.valid_to.is_(None))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_baselines(session: AsyncSession, patient_id: int) -> Sequence[BaselineRoutine]:
    stmt = (
        select(BaselineRoutine)
        .where(BaselineRoutine.patient_id == patient_id)
        .order_by(BaselineRoutine.valid_from.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def create_baseline(session: AsyncSession, data: dict) -> BaselineRoutine:
    baseline = BaselineRoutine(**data)
    session.add(baseline)
    await session.flush()
    await session.refresh(baseline)
    return baseline


async def close_active_baseline(session: AsyncSession, baseline: BaselineRoutine, valid_to: date) -> None:
    await session.execute(
        update(BaselineRoutine)
        .where(BaselineRoutine.id == baseline.id)
        .values(valid_to=valid_to)
    )


# --- DailyPlan ---


async def get_plan_by_date(
    session: AsyncSession,
    *,
    patient_id: int,
    plan_date: date,
) -> Optional[DailyPlan]:
    stmt = (
        select(DailyPlan)
        .where(DailyPlan.patient_id == patient_id)
        .where(DailyPlan.plan_date == plan_date)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_plan(
    session: AsyncSession,
    *,
    patient_id: int,
    plan_date: date,
    data: dict,
) -> DailyPlan:
    """Создать новый план или обновить существующий, увеличивая edit_count."""
    existing = await get_plan_by_date(session, patient_id=patient_id, plan_date=plan_date)
    if existing is None:
        plan = DailyPlan(
            patient_id=patient_id,
            plan_date=plan_date,
            **data,
        )
        session.add(plan)
        await session.flush()
        await session.refresh(plan)
        return plan

    # Обновляем существующий план: edit_count += 1
    await session.execute(
        update(DailyPlan)
        .where(DailyPlan.id == existing.id)
        .values(
            edit_count=DailyPlan.edit_count + 1,
            **data,
        )
    )
    await session.refresh(existing)
    return existing


# --- DailyVerification ---


async def get_verification_by_date(
    session: AsyncSession,
    *,
    patient_id: int,
    verification_date: date,
) -> Optional[DailyVerification]:
    stmt = (
        select(DailyVerification)
        .where(DailyVerification.patient_id == patient_id)
        .where(DailyVerification.verification_date == verification_date)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_verification(
    session: AsyncSession,
    *,
    patient_id: int,
    verification_date: date,
    data: dict,
) -> DailyVerification:
    """Создать или обновить верификацию, увеличивая edit_count."""
    existing = await get_verification_by_date(
        session,
        patient_id=patient_id,
        verification_date=verification_date,
    )
    if existing is None:
        ver = DailyVerification(
            patient_id=patient_id,
            verification_date=verification_date,
            **data,
        )
        session.add(ver)
        await session.flush()
        await session.refresh(ver)
        return ver

    await session.execute(
        update(DailyVerification)
        .where(DailyVerification.id == existing.id)
        .values(
            edit_count=DailyVerification.edit_count + 1,
            **data,
        )
    )
    await session.refresh(existing)
    return existing


