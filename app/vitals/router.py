# ============================================
# Vitals API: Эндпоинты витальных показателей
# ============================================
# REST API для записи и чтения витальных данных пациента:
# артериальное давление, пульс, вес, водный баланс.
# Каждый тип имеет общие эндпоинты и /me-эндпоинты (текущий пользователь).

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.vitals import crud, schemas, service
from app.auth.dependencies import get_current_user
from app.notifications.badge_service import check_tracker_badges, check_vitals_full_day
from app.users.models import User
from core.db.session import async_session_factory, get_async_session


router = APIRouter(prefix="/vitals", tags=["vitals"])


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


def _parse_order(order_by: Optional[str]) -> str:
    if not order_by:
        return "measured_at desc"
    return order_by


# ============================================
#   АД (артериальное давление)
# ============================================

@router.post("/bp", response_model=schemas.BPMeasurementRead)
async def create_bp(
    payload: schemas.BPMeasurementCreate,
    session: AsyncSession = Depends(get_session),
):
    prepared = service.VitalsService.prepare_bp_data(**payload.model_dump())
    measurement = await crud.bp_crud.create(session, prepared)
    await session.commit()
    return measurement


@router.get("/bp", response_model=list[schemas.BPMeasurementRead])
async def list_bp(
    *,
    session: AsyncSession = Depends(get_session),
    user_id: Optional[int] = None,
    limit: int = Query(100, le=200),
    offset: int = 0,
    order_by: Optional[str] = Query("measured_at desc"),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
):
    records = await crud.bp_crud.list(
        session,
        user_id=user_id,
        limit=limit,
        offset=offset,
        order_by=_parse_order(order_by),
        date_from=date_from,
        date_to=date_to,
    )
    return records


@router.get("/bp/me", response_model=list[schemas.BPMeasurementRead])
async def list_bp_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    limit: int = Query(100, le=200),
    offset: int = 0,
    order_by: Optional[str] = Query("measured_at desc"),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
):
    records = await crud.bp_crud.list(
        session,
        user_id=user.id,
        limit=limit,
        offset=offset,
        order_by=_parse_order(order_by),
        date_from=date_from,
        date_to=date_to,
    )
    return records


@router.post("/bp/me", response_model=schemas.BPMeasurementRead)
async def create_bp_me(
    payload: schemas.BPMeasurementCreateMe,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    prepared = service.VitalsService.prepare_bp_data(
        user_id=user.id,
        systolic=payload.systolic,
        diastolic=payload.diastolic,
        pulse=payload.pulse,
        session_id=payload.session_id,
        measured_at=payload.measured_at,
        context=payload.context,
    )
    measurement = await crud.bp_crud.create(session, prepared)
    await session.commit()
    await session.refresh(measurement)
    await check_tracker_badges(user.id, "vitals", session)
    await check_vitals_full_day(user.id, session)
    await session.commit()
    return measurement


# ============================================
#   Пульс
# ============================================

@router.post("/pulse", response_model=schemas.PulseMeasurementRead)
async def create_pulse(
    payload: schemas.PulseMeasurementCreate,
    session: AsyncSession = Depends(get_session),
):
    prepared = service.VitalsService.prepare_pulse_data(**payload.model_dump())
    measurement = await crud.pulse_crud.create(session, prepared)
    await session.commit()
    return measurement


@router.get("/pulse", response_model=list[schemas.PulseMeasurementRead])
async def list_pulse(
    *,
    session: AsyncSession = Depends(get_session),
    user_id: Optional[int] = None,
    limit: int = Query(100, le=200),
    offset: int = 0,
    order_by: Optional[str] = Query("measured_at desc"),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
):
    records = await crud.pulse_crud.list(
        session,
        user_id=user_id,
        limit=limit,
        offset=offset,
        order_by=_parse_order(order_by),
        date_from=date_from,
        date_to=date_to,
    )
    return records


@router.get("/pulse/me", response_model=list[schemas.PulseMeasurementRead])
async def list_pulse_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    limit: int = Query(100, le=200),
    offset: int = 0,
    order_by: Optional[str] = Query("measured_at desc"),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
):
    records = await crud.pulse_crud.list(
        session, user_id=user.id, limit=limit, offset=offset,
        order_by=_parse_order(order_by), date_from=date_from, date_to=date_to,
    )
    return records


@router.post("/pulse/me", response_model=schemas.PulseMeasurementRead)
async def create_pulse_me(
    payload: schemas.PulseMeasurementCreateMe,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    prepared = service.VitalsService.prepare_pulse_data(
        user_id=user.id,
        bpm=payload.bpm,
        session_id=payload.session_id,
        measured_at=payload.measured_at,
        context=payload.context,
    )
    measurement = await crud.pulse_crud.create(session, prepared)
    await session.commit()
    await check_vitals_full_day(user.id, session)
    await session.commit()
    return measurement


# ============================================
#   Вес
# ============================================

@router.post("/weight", response_model=schemas.WeightMeasurementRead)
async def create_weight(
    payload: schemas.WeightMeasurementCreate,
    session: AsyncSession = Depends(get_session),
):
    prepared = service.VitalsService.prepare_weight_data(**payload.model_dump())
    measurement = await crud.weight_crud.create(session, prepared)
    await session.commit()
    return measurement


@router.get("/weight", response_model=list[schemas.WeightMeasurementRead])
async def list_weight(
    *,
    session: AsyncSession = Depends(get_session),
    user_id: Optional[int] = None,
    limit: int = Query(100, le=200),
    offset: int = 0,
    order_by: Optional[str] = Query("measured_at desc"),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
):
    records = await crud.weight_crud.list(
        session,
        user_id=user_id,
        limit=limit,
        offset=offset,
        order_by=_parse_order(order_by),
        date_from=date_from,
        date_to=date_to,
    )
    return records


@router.get("/weight/me", response_model=list[schemas.WeightMeasurementRead])
async def list_weight_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    limit: int = Query(100, le=200),
    offset: int = 0,
    order_by: Optional[str] = Query("measured_at desc"),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
):
    records = await crud.weight_crud.list(
        session, user_id=user.id, limit=limit, offset=offset,
        order_by=_parse_order(order_by), date_from=date_from, date_to=date_to,
    )
    return records


@router.post("/weight/me", response_model=schemas.WeightMeasurementRead)
async def create_weight_me(
    payload: schemas.WeightMeasurementCreateMe,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    prepared = service.VitalsService.prepare_weight_data(
        user_id=user.id,
        weight=payload.weight,
        session_id=payload.session_id,
        measured_at=payload.measured_at,
        context=payload.context,
    )
    measurement = await crud.weight_crud.create(session, prepared)
    await session.commit()
    await check_vitals_full_day(user.id, session)
    await session.commit()
    return measurement


# ============================================
#   Вода (водный баланс)
# ============================================

@router.post("/water", response_model=schemas.WaterIntakeRead)
async def create_water(
    payload: schemas.WaterIntakeCreate,
    session: AsyncSession = Depends(get_session),
):
    prepared = service.VitalsService.prepare_water_data(**payload.model_dump())
    measurement = await crud.water_crud.create(session, prepared)
    await session.commit()
    return measurement


@router.post("/water/me", response_model=schemas.WaterIntakeRead)
async def create_water_me(
    payload: schemas.WaterIntakeCreateMe,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    prepared = service.VitalsService.prepare_water_data(
        user_id=user.id,
        volume_ml=payload.volume_ml,
        liquid_type=payload.liquid_type,
        session_id=payload.session_id,
        measured_at=payload.measured_at,
        context=payload.context,
    )
    measurement = await crud.water_crud.create(session, prepared)
    await session.commit()
    await check_vitals_full_day(user.id, session)
    await session.commit()
    return measurement


@router.get("/water/me", response_model=list[schemas.WaterIntakeRead])
async def list_water_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    limit: int = Query(100, le=200),
    offset: int = 0,
    order_by: Optional[str] = Query("measured_at desc"),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
):
    records = await crud.water_crud.list(
        session, user_id=user.id, limit=limit, offset=offset,
        order_by=_parse_order(order_by), date_from=date_from, date_to=date_to,
    )
    return records


@router.get("/water/daily-total/me")
async def get_daily_water_total_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    date: Optional[datetime] = Query(None),
):
    target_date = date or datetime.now()
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    records = await crud.water_crud.list(
        session, user_id=user.id, limit=1000,
        date_from=start_of_day, date_to=end_of_day,
    )
    total_ml = sum(r.volume_ml for r in records)
    return {"date": start_of_day, "total_ml": total_ml, "entries_count": len(records), "entries": records}


@router.delete("/water/{measurement_id}")
async def delete_water(
    measurement_id: str, # UUID передаем как строку, FastAPI сконвертит
    session: AsyncSession = Depends(get_session),
):
    # TODO: Проверка прав доступа если нужно (сейчас удаляем просто по ID)
    await crud.water_crud.delete(session, measurement_id)
    await session.commit()
    return {"ok": True}
