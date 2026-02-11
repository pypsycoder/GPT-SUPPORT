# ============================================
# Medications API: reference, CRUD, schedule, intake, settings
# ============================================

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.medications import schemas
from app.medications.models import IntakeStatus, MedicationCategory
from app.medications.service import (
    archive_medication,
    create_medication,
    get_medication,
    get_medication_history,
    get_or_create_settings,
    get_schedule,
    list_intakes,
    list_medications,
    search_references,
    update_medication,
    update_settings,
    upsert_intake,
)
from app.users.models import User
from core.db.session import get_async_session


router = APIRouter(prefix="/medications", tags=["medications"])


@router.get("/reference", response_model=schemas.MedicationReferenceListOut)
async def get_reference_list(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    search: str | None = Query(None, description="Поиск по названию"),
    category: MedicationCategory | None = Query(None, description="Фильтр по категории"),
    limit: int = Query(50, ge=1, le=100),
):
    """Список препаратов справочника для автокомплита."""
    items, total = await search_references(
        session,
        search=search,
        category=category.value if category else None,
        limit=limit,
    )
    return schemas.MedicationReferenceListOut(
        items=[schemas.MedicationReferenceOut.model_validate(r) for r in items],
        total=total,
    )


@router.get("", response_model=schemas.MedicationListOut)
async def get_my_medications(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    active_only: bool = Query(True, description="Только активные"),
):
    """Список препаратов текущего пользователя."""
    meds = await list_medications(session, user_id=user.id, active_only=active_only)
    return schemas.MedicationListOut(
        items=[schemas.MedicationOut.model_validate(m) for m in meds],
        total=len(meds),
    )


@router.post("", response_model=schemas.MedicationOut)
async def add_medication(
    payload: schemas.MedicationCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Добавить препарат."""
    med = await create_medication(session, user_id=user.id, payload=payload)
    await session.commit()
    await session.refresh(med)
    return schemas.MedicationOut.model_validate(med)


@router.patch("/{medication_id}", response_model=schemas.MedicationOut)
async def patch_medication(
    medication_id: UUID,
    payload: schemas.MedicationUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Обновить препарат (текущее состояние сохраняется в историю)."""
    med = await update_medication(
        session,
        medication_id=medication_id,
        user_id=user.id,
        payload=payload,
    )
    if med is None:
        raise HTTPException(status_code=404, detail="Препарат не найден")
    await session.commit()
    await session.refresh(med)
    return schemas.MedicationOut.model_validate(med)


@router.delete("/{medication_id}", status_code=204)
async def delete_medication(
    medication_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Архивировать препарат (не удалять)."""
    ok = await archive_medication(session, medication_id=medication_id, user_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Препарат не найден")
    await session.commit()


@router.get("/{medication_id}/history", response_model=list[schemas.MedicationHistoryOut])
async def get_medication_history_endpoint(
    medication_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """История изменений препарата."""
    history = await get_medication_history(session, medication_id=medication_id, user_id=user.id)
    return [schemas.MedicationHistoryOut.model_validate(h) for h in history]


@router.get("/schedule", response_model=schemas.DayScheduleOut)
async def get_day_schedule(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    qdate: date | None = Query(None, alias="date", description="Дата (по умолчанию сегодня)"),
):
    """Расписание на день (генерируется на лету)."""
    target = qdate if qdate is not None else date.today()
    schedule = await get_schedule(session, user_id=user.id, target_date=target)
    return schedule


@router.post("/intake", response_model=schemas.IntakeRecordOut)
async def record_intake(
    payload: schemas.IntakeRecordCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Отметить приём или пропуск."""
    intake = await upsert_intake(session, user_id=user.id, payload=payload)
    if intake is None:
        raise HTTPException(
            status_code=404,
            detail="Препарат не найден или не активен",
        )
    await session.commit()
    await session.refresh(intake)
    med = await get_medication(session, intake.medication_id, user_id=user.id)
    name = med.display_name if med else ""
    return schemas.IntakeRecordOut(
        id=intake.id,
        medication_id=intake.medication_id,
        medication_name=name,
        scheduled_date=intake.scheduled_date,
        scheduled_time=intake.scheduled_time,
        status=IntakeStatus(intake.status),
        taken_at=intake.taken_at,
        created_at=intake.created_at,
    )


@router.get("/intake/history", response_model=list[schemas.IntakeRecordOut])
async def get_intake_history(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    medication_id: UUID | None = Query(None),
    status: IntakeStatus | None = Query(None),
):
    """История приёмов."""
    intakes = await list_intakes(
        session,
        user_id=user.id,
        from_date=from_date,
        to_date=to_date,
        medication_id=medication_id,
        status=status.value if status else None,
    )
    result = []
    for intake in intakes:
        med = await get_medication(session, intake.medication_id, user_id=user.id)
        name = med.display_name if med else ""
        result.append(
            schemas.IntakeRecordOut(
                id=intake.id,
                medication_id=intake.medication_id,
                medication_name=name,
                scheduled_date=intake.scheduled_date,
                scheduled_time=intake.scheduled_time,
                status=IntakeStatus(intake.status),
                taken_at=intake.taken_at,
                created_at=intake.created_at,
            )
        )
    return result


@router.get("/settings", response_model=schemas.MedicationSettingsOut)
async def get_my_settings(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Настройки модуля лекарств."""
    settings = await get_or_create_settings(session, user_id=user.id)
    await session.commit()
    return schemas.MedicationSettingsOut(tracking_enabled=settings.tracking_enabled)


@router.patch("/settings", response_model=schemas.MedicationSettingsOut)
async def patch_my_settings(
    payload: schemas.MedicationSettingsUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Обновить настройки модуля."""
    settings = await update_settings(session, user_id=user.id, payload=payload)
    await session.commit()
    await session.refresh(settings)
    return schemas.MedicationSettingsOut(tracking_enabled=settings.tracking_enabled)
