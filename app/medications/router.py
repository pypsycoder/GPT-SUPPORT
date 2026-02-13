# ============================================
# Medications API: Prescriptions & Intakes CRUD
# Prefix: /patient/medications  (registered with /api in main.py)
# ============================================

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.medications import schemas
from app.medications.service import (
    calculate_adherence_rate,
    check_duplicate_intake,
    create_intake,
    create_prescription,
    delete_intake,
    delete_prescription,
    get_intake,
    get_intakes_for_prescription,
    get_prescription,
    list_intakes,
    list_prescriptions,
    update_intake,
    update_prescription,
)
from app.users.models import User
from core.db.session import get_async_session

router = APIRouter(prefix="/patient/medications", tags=["medications"])


# ── Prescriptions ─────────────────────────────────────────────────


@router.get("/prescriptions", response_model=list[schemas.PrescriptionResponse])
async def get_prescriptions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    status: str = Query("active", description="active | inactive | all"),
):
    """Список назначений текущего пациента с adherence_rate."""
    prescriptions = await list_prescriptions(session, patient_id=user.id, status=status)
    result = []
    for p in prescriptions:
        intakes = await get_intakes_for_prescription(session, p.id)
        rate = calculate_adherence_rate(p, intakes)
        resp = schemas.PrescriptionResponse(
            id=p.id,
            patient_id=p.patient_id,
            medication_name=p.medication_name,
            dose=p.dose,
            dose_unit=p.dose_unit,
            frequency_times_per_day=p.frequency_times_per_day,
            intake_schedule=p.intake_schedule,
            route=p.route,
            start_date=p.start_date,
            end_date=p.end_date,
            indication=p.indication,
            instructions=p.instructions,
            status=p.status,
            prescribed_by=p.prescribed_by,
            adherence_rate=rate,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        result.append(resp)
    return result


@router.get("/prescriptions/{prescription_id}", response_model=schemas.PrescriptionResponse)
async def get_prescription_endpoint(
    prescription_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Детали одного назначения."""
    p = await get_prescription(session, prescription_id, patient_id=user.id)
    if p is None:
        raise HTTPException(status_code=404, detail="Назначение не найдено")
    intakes = await get_intakes_for_prescription(session, p.id)
    rate = calculate_adherence_rate(p, intakes)
    return schemas.PrescriptionResponse(
        id=p.id,
        patient_id=p.patient_id,
        medication_name=p.medication_name,
        dose=p.dose,
        dose_unit=p.dose_unit,
        frequency_times_per_day=p.frequency_times_per_day,
        intake_schedule=p.intake_schedule,
        route=p.route,
        start_date=p.start_date,
        end_date=p.end_date,
        indication=p.indication,
        instructions=p.instructions,
        status=p.status,
        prescribed_by=p.prescribed_by,
        adherence_rate=rate,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.post(
    "/prescriptions",
    response_model=schemas.PrescriptionResponse,
    status_code=201,
)
async def create_prescription_endpoint(
    payload: schemas.PrescriptionCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Создать назначение."""
    p = await create_prescription(session, patient_id=user.id, payload=payload)
    await session.commit()
    await session.refresh(p)
    return schemas.PrescriptionResponse(
        id=p.id,
        patient_id=p.patient_id,
        medication_name=p.medication_name,
        dose=p.dose,
        dose_unit=p.dose_unit,
        frequency_times_per_day=p.frequency_times_per_day,
        intake_schedule=p.intake_schedule,
        route=p.route,
        start_date=p.start_date,
        end_date=p.end_date,
        indication=p.indication,
        instructions=p.instructions,
        status=p.status,
        prescribed_by=p.prescribed_by,
        adherence_rate=0.0,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.put("/prescriptions/{prescription_id}", response_model=schemas.PrescriptionResponse)
async def update_prescription_endpoint(
    prescription_id: int,
    payload: schemas.PrescriptionUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Обновить назначение. 403 если врачебное (prescribed_by IS NOT NULL)."""
    p = await get_prescription(session, prescription_id, patient_id=user.id)
    if p is None:
        raise HTTPException(status_code=404, detail="Назначение не найдено")
    if p.prescribed_by is not None:
        raise HTTPException(
            status_code=403,
            detail="Нельзя редактировать врачебное назначение",
        )
    p = await update_prescription(session, prescription_id, patient_id=user.id, payload=payload)
    await session.commit()
    await session.refresh(p)
    intakes = await get_intakes_for_prescription(session, p.id)
    rate = calculate_adherence_rate(p, intakes)
    return schemas.PrescriptionResponse(
        id=p.id,
        patient_id=p.patient_id,
        medication_name=p.medication_name,
        dose=p.dose,
        dose_unit=p.dose_unit,
        frequency_times_per_day=p.frequency_times_per_day,
        intake_schedule=p.intake_schedule,
        route=p.route,
        start_date=p.start_date,
        end_date=p.end_date,
        indication=p.indication,
        instructions=p.instructions,
        status=p.status,
        prescribed_by=p.prescribed_by,
        adherence_rate=rate,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.delete("/prescriptions/{prescription_id}", status_code=204)
async def delete_prescription_endpoint(
    prescription_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Удалить назначение. 403 если врачебное. Каскадно удаляет intakes."""
    p = await get_prescription(session, prescription_id, patient_id=user.id)
    if p is None:
        raise HTTPException(status_code=404, detail="Назначение не найдено")
    if p.prescribed_by is not None:
        raise HTTPException(
            status_code=403,
            detail="Нельзя удалить врачебное назначение",
        )
    await delete_prescription(session, prescription_id, patient_id=user.id)
    await session.commit()


# ── Intakes ───────────────────────────────────────────────────────


@router.get("/intakes", response_model=list[schemas.IntakeResponse])
async def get_intakes(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    prescription_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Список приёмов (сортировка: intake_datetime DESC)."""
    intakes = await list_intakes(
        session,
        patient_id=user.id,
        prescription_id=prescription_id,
        limit=limit,
        offset=offset,
    )
    return [schemas.IntakeResponse.model_validate(i) for i in intakes]


@router.get("/intakes/{intake_id}", response_model=schemas.IntakeResponse)
async def get_intake_endpoint(
    intake_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Получить один приём."""
    intake = await get_intake(session, intake_id, patient_id=user.id)
    if intake is None:
        raise HTTPException(status_code=404, detail="Запись о приёме не найдена")
    return schemas.IntakeResponse.model_validate(intake)


@router.post("/intakes", response_model=schemas.IntakeResponse, status_code=201)
async def create_intake_endpoint(
    payload: schemas.IntakeCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Создать запись о приёме.
    - is_retrospective = true если intake_datetime < now() - 30 мин
    - intake_datetime не позже now()
    - intake_datetime не раньше now() - 24h
    - 409 если уже есть приём для этого prescription_id с |diff| < 5 минут
    """
    now = datetime.now(timezone.utc)

    # Проверка: prescription принадлежит пациенту
    p = await get_prescription(session, payload.prescription_id, patient_id=user.id)
    if p is None:
        raise HTTPException(status_code=404, detail="Назначение не найдено")

    # Валидация: не в будущем
    if payload.intake_datetime > now:
        raise HTTPException(
            status_code=400,
            detail="Время приёма не может быть в будущем",
        )

    # Валидация: не старше 24 часов
    if payload.intake_datetime < now - timedelta(hours=24):
        raise HTTPException(
            status_code=400,
            detail="Нельзя отметить приём старше 24 часов",
        )

    # Проверка дубликата (|diff| < 5 мин)
    is_dup = await check_duplicate_intake(
        session, payload.prescription_id, payload.intake_datetime
    )
    if is_dup:
        raise HTTPException(
            status_code=409,
            detail="Приём для этого препарата уже отмечен в указанное время",
        )

    intake = await create_intake(session, patient_id=user.id, payload=payload)
    await session.commit()
    await session.refresh(intake)
    return schemas.IntakeResponse.model_validate(intake)


@router.put("/intakes/{intake_id}", response_model=schemas.IntakeResponse)
async def update_intake_endpoint(
    intake_id: int,
    payload: schemas.IntakeUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Обновить запись о приёме."""
    intake = await update_intake(session, intake_id, patient_id=user.id, payload=payload)
    if intake is None:
        raise HTTPException(status_code=404, detail="Запись о приёме не найдена")
    await session.commit()
    await session.refresh(intake)
    return schemas.IntakeResponse.model_validate(intake)


@router.delete("/intakes/{intake_id}", status_code=204)
async def delete_intake_endpoint(
    intake_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Удалить запись о приёме."""
    intake = await delete_intake(session, intake_id, patient_id=user.id)
    if intake is None:
        raise HTTPException(status_code=404, detail="Запись о приёме не найдена")
    await session.commit()
