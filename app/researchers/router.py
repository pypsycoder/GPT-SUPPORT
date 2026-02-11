# ============================================
# Researchers API: Панель исследователя
# ============================================
# Эндпоинты для создания пациентов, сброса PIN,
# просмотра списка пациентов и их данных.

"""API endpoints for researcher patient management."""

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.session import get_async_session
from app.auth.dependencies import get_current_researcher
from app.researchers.models import Researcher
from app.researchers.schemas import (
    PatientCreateRequest,
    PatientCreateResponse,
    PatientListItem,
    PatientDetail,
    PatientCenterAssign,
    PinResetResponse,
)
from app.researchers import crud

router = APIRouter(prefix="/researcher", tags=["researcher"])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/stats")
async def researcher_stats(
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Return basic patient statistics and usage stats for the researcher dashboard."""
    patient_stats = await crud.get_patients_stats(session)
    usage_stats = await crud.get_usage_stats(session)
    return {
        **patient_stats,
        "usage": usage_stats,
    }


# ---------------------------------------------------------------------------
# Patient list / create
# ---------------------------------------------------------------------------

def _patient_to_list_item(p) -> PatientListItem:
    """Build PatientListItem with center info from joined User."""
    return PatientListItem(
        id=p.id,
        patient_number=p.patient_number,
        full_name=p.full_name,
        age=p.age,
        gender=p.gender,
        is_locked=p.is_locked or False,
        consent_personal_data=p.consent_personal_data or False,
        consent_bot_use=p.consent_bot_use or False,
        center_id=str(p.center_id) if p.center_id else None,
        center_name=p.center.name if p.center else None,
        center_city=p.center.city if p.center else None,
    )


@router.get("/patients", response_model=List[PatientListItem])
async def list_patients(
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Return all patients."""
    patients = await crud.list_patients(session)
    return [_patient_to_list_item(p) for p in patients]


@router.post("/patients", response_model=PatientCreateResponse, status_code=201)
async def create_patient(
    body: PatientCreateRequest,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new patient. Returns the generated PIN (shown only once)."""
    user, pin = await crud.create_patient(
        session,
        full_name=body.full_name,
        age=body.age,
        gender=body.gender,
    )
    return PatientCreateResponse(
        id=user.id,
        patient_number=user.patient_number,
        pin=pin,
        full_name=user.full_name,
    )


# ---------------------------------------------------------------------------
# Single patient
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}", response_model=PatientDetail)
async def get_patient(
    patient_id: int,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Return details of a single patient."""
    user = await crud.get_patient_by_id(session, patient_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    return PatientDetail.model_validate(user)


@router.post("/patients/{patient_id}/reset-pin", response_model=PinResetResponse)
async def reset_pin(
    patient_id: int,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Reset the patient's PIN and unlock the account."""
    user = await crud.get_patient_by_id(session, patient_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    new_pin = await crud.reset_patient_pin(session, user)
    return PinResetResponse(patient_number=user.patient_number, new_pin=new_pin)


@router.post("/patients/{patient_id}/unlock")
async def unlock_patient(
    patient_id: int,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Unlock a locked patient account."""
    user = await crud.get_patient_by_id(session, patient_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    await crud.unlock_patient(session, user)
    return {"ok": True, "message": "Аккаунт разблокирован"}


@router.patch("/patients/{patient_id}/center")
async def assign_patient_center(
    patient_id: int,
    body: PatientCenterAssign,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Assign or clear dialysis center for a patient."""
    user = await crud.get_patient_by_id(session, patient_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    center_id: UUID | None = body.center_id
    if center_id is not None:
        from app.dialysis.crud import get_center_by_id
        center = await get_center_by_id(session, center_id)
        if center is None:
            raise HTTPException(status_code=400, detail="Центр диализа не найден")
    await crud.update_patient_center(session, user, center_id)
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.users.models import User
    result = await session.execute(
        select(User).where(User.id == patient_id).options(selectinload(User.center))
    )
    user = result.scalar_one()
    return _patient_to_list_item(user)
