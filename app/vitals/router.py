from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.vitals import crud, schemas, service
from app.users import crud as users_crud
from core.db.session import async_session_factory


router = APIRouter(prefix="/vitals", tags=["vitals"])


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


def _parse_order(order_by: Optional[str]) -> str:
    if not order_by:
        return "measured_at desc"
    return order_by


# =========================
#  АД
# =========================

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


@router.get("/bp/by-token/{patient_token}", response_model=list[schemas.BPMeasurementRead])
async def list_bp_by_token(
    patient_token: str,
    *,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(100, le=200),
    offset: int = 0,
    order_by: Optional[str] = Query("measured_at desc"),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
):
    user = await users_crud.get_user_by_patient_token(session, patient_token=patient_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пациент с таким токеном не найден",
        )

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


@router.post("/bp/by-token/{patient_token}", response_model=schemas.BPMeasurementRead)
async def create_bp_by_token(
    patient_token: str,
    payload: schemas.BPMeasurementCreate,
    session: AsyncSession = Depends(get_session),
):
    user = await users_crud.get_user_by_patient_token(session, patient_token=patient_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пациент с таким токеном не найден",
        )

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
    return measurement


# =========================
#  Пульс
# =========================

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


@router.get("/pulse/by-token/{patient_token}", response_model=list[schemas.PulseMeasurementRead])
async def list_pulse_by_token(
    patient_token: str,
    *,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(100, le=200),
    offset: int = 0,
    order_by: Optional[str] = Query("measured_at desc"),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
):
    user = await users_crud.get_user_by_patient_token(session, patient_token=patient_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пациент с таким токеном не найден",
        )

    records = await crud.pulse_crud.list(
        session,
        user_id=user.id,
        limit=limit,
        offset=offset,
        order_by=_parse_order(order_by),
        date_from=date_from,
        date_to=date_to,
    )
    return records


@router.post("/pulse/by-token/{patient_token}", response_model=schemas.PulseMeasurementRead)
async def create_pulse_by_token(
    patient_token: str,
    payload: schemas.PulseMeasurementCreate,
    session: AsyncSession = Depends(get_session),
):
    user = await users_crud.get_user_by_patient_token(session, patient_token=patient_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пациент с таким токеном не найден",
        )

    prepared = service.VitalsService.prepare_pulse_data(
        user_id=user.id,
        bpm=payload.bpm,
        session_id=payload.session_id,
        measured_at=payload.measured_at,
        context=payload.context,
    )

    measurement = await crud.pulse_crud.create(session, prepared)
    await session.commit()
    return measurement


# =========================
#  Вес
# =========================

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


@router.get("/weight/by-token/{patient_token}", response_model=list[schemas.WeightMeasurementRead])
async def list_weight_by_token(
    patient_token: str,
    *,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(100, le=200),
    offset: int = 0,
    order_by: Optional[str] = Query("measured_at desc"),
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
):
    user = await users_crud.get_user_by_patient_token(session, patient_token=patient_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пациент с таким токеном не найден",
        )

    records = await crud.weight_crud.list(
        session,
        user_id=user.id,
        limit=limit,
        offset=offset,
        order_by=_parse_order(order_by),
        date_from=date_from,
        date_to=date_to,
    )
    return records


@router.post("/weight/by-token/{patient_token}", response_model=schemas.WeightMeasurementRead)
async def create_weight_by_token(
    patient_token: str,
    payload: schemas.WeightMeasurementCreate,
    session: AsyncSession = Depends(get_session),
):
    user = await users_crud.get_user_by_patient_token(session, patient_token=patient_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пациент с таким токеном не найден",
        )

    prepared = service.VitalsService.prepare_weight_data(
        user_id=user.id,
        weight=payload.weight,
        session_id=payload.session_id,
        measured_at=payload.measured_at,
        context=payload.context,
    )

    measurement = await crud.weight_crud.create(session, prepared)
    await session.commit()
    return measurement
