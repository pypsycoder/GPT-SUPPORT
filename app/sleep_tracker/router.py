# ============================================
# Sleep Tracker API: создание, чтение по дате, обновление, список
# ============================================

from __future__ import annotations

import datetime
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.sleep_tracker import crud, schemas, service
from app.auth.dependencies import get_current_user
from app.dialysis.service import is_dialysis_day
from app.users.models import User
from core.db.session import get_async_session


router = APIRouter(prefix="/sleep", tags=["sleep"])


@router.get("/me/by-date", response_model=schemas.SleepRecordRead)
async def get_sleep_record_by_date_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    qdate: date = Query(..., alias="date", description="Дата ночи (sleep_date) YYYY-MM-DD"),
):
    """Получить запись сна за выбранную ночь (для проверки дубликата и предзаполнения формы)."""
    record = await crud.get_by_patient_and_date(session, patient_id=user.id, sleep_date=qdate)
    if record is None:
        raise HTTPException(status_code=404, detail="Запись за эту ночь не найдена")
    return record


@router.post("/me", response_model=schemas.SleepRecordRead)
async def create_sleep_record_me(
    payload: schemas.SleepRecordCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Создать запись сна за выбранную ночь (текущий пациент). sleep_date передаётся с фронта."""
    submitted_at = datetime.datetime.now(datetime.timezone.utc)
    report_date = submitted_at.date()
    dialysis_day = await is_dialysis_day(session, patient_id=user.id, date=report_date)

    data = service.SleepTrackerService.prepare_record(
        patient_id=user.id,
        payload=payload,
        submitted_at=submitted_at,
        dialysis_day=dialysis_day,
    )
    record = await crud.create(session, data)
    await session.commit()
    await session.refresh(record)
    return record


@router.put("/me/{record_id}", response_model=schemas.SleepRecordRead)
async def update_sleep_record_me(
    record_id: UUID,
    payload: schemas.SleepRecordUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Обновить существующую запись сна. updated_at и edit_count обновляются автоматически."""
    existing = await crud.get_by_id(session, record_id)
    if existing is None or existing.patient_id != user.id:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    update_data = service.SleepTrackerService.prepare_update(payload)
    record = await crud.update_record(session, record_id=record_id, patient_id=user.id, update_data=update_data)
    await session.commit()
    if record:
        await session.refresh(record)
    return record


@router.get("/me", response_model=list[schemas.SleepRecordRead])
async def list_sleep_records_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    limit: int = Query(100, le=200),
    offset: int = 0,
):
    """Список записей сна текущего пациента (по sleep_date, новые сверху)."""
    records = await crud.list_by_patient(
        session,
        patient_id=user.id,
        limit=limit,
        offset=offset,
    )
    return list(records)
