from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.vitals import crud, schemas, service
from core.db.session import async_session_factory

router = APIRouter(prefix="/vitals", tags=["vitals"])


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


def _parse_order(order_by: Optional[str]) -> str:
    if not order_by:
        return "measured_at desc"
    return order_by


@router.post("/bp", response_model=schemas.BPMeasurementRead)
async def create_bp(
    payload: schemas.BPMeasurementCreate, session: AsyncSession = Depends(get_session)
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


@router.post("/pulse", response_model=schemas.PulseMeasurementRead)
async def create_pulse(
    payload: schemas.PulseMeasurementCreate, session: AsyncSession = Depends(get_session)
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


@router.post("/weight", response_model=schemas.WeightMeasurementRead)
async def create_weight(
    payload: schemas.WeightMeasurementCreate, session: AsyncSession = Depends(get_session)
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

