# ============================================
# Medications Service: schedule, CRUD, history, intake, settings
# ============================================

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from typing import Sequence
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.medications.models import (
    FoodRelation,
    FrequencyType,
    IntakeStatus,
    Medication,
    MedicationHistory,
    MedicationIntake,
    MedicationReference,
    UserMedicationSettings,
)

from app.medications import schemas


# --- Day names (0=пн .. 6=вс) ---

DAY_NAMES_RU = {
    0: "понедельник",
    1: "вторник",
    2: "среда",
    3: "четверг",
    4: "пятница",
    5: "суббота",
    6: "воскресенье",
}

DAY_NAMES_SHORT_RU = {
    0: "пн",
    1: "вт",
    2: "ср",
    3: "чт",
    4: "пт",
    5: "сб",
    6: "вс",
}


def get_day_name_ru(day: int, short: bool = False) -> str:
    names = DAY_NAMES_SHORT_RU if short else DAY_NAMES_RU
    return names.get(day, "")


FOOD_RELATION_LABELS = {
    FoodRelation.before: "до еды",
    FoodRelation.with_meal: "во время еды",
    FoodRelation.after: "после еды",
    FoodRelation.none: "",
}


def format_food_relation(relation: FoodRelation | None) -> str:
    if relation is None or relation == FoodRelation.none:
        return ""
    return FOOD_RELATION_LABELS.get(relation, "")


# --- Reference search ---


async def search_references(
    session: AsyncSession,
    search: str | None = None,
    category: str | None = None,
    limit: int = 50,
) -> tuple[list[MedicationReference], int]:
    """Search references: ILIKE on name_ru, name_trade, search_keywords; filter by category; sort by sort_order, name_ru."""
    stmt = select(MedicationReference)
    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                MedicationReference.name_ru.ilike(term),
                MedicationReference.name_trade.ilike(term),
                MedicationReference.search_keywords.ilike(term),
            )
        )
    if category:
        stmt = stmt.where(MedicationReference.category == category)
    stmt = stmt.order_by(MedicationReference.sort_order, MedicationReference.name_ru)
    result = await session.execute(stmt)
    all_rows = result.scalars().all()
    total = len(all_rows)
    items = all_rows[:limit]
    return list(items), total


# --- Medications CRUD ---


async def list_medications(
    session: AsyncSession,
    user_id: int,
    active_only: bool = True,
) -> Sequence[Medication]:
    stmt = select(Medication).where(Medication.user_id == user_id)
    if active_only:
        stmt = stmt.where(Medication.is_active.is_(True))
    stmt = stmt.order_by(Medication.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_medication(
    session: AsyncSession,
    medication_id: UUID,
    user_id: int | None = None,
) -> Medication | None:
    stmt = select(Medication).where(Medication.id == medication_id)
    if user_id is not None:
        stmt = stmt.where(Medication.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_medication(
    session: AsyncSession,
    user_id: int,
    payload: schemas.MedicationCreate,
) -> Medication:
    days = payload.days_of_week if payload.frequency_type == FrequencyType.specific_days else None
    med = Medication(
        user_id=user_id,
        reference_id=payload.reference_id,
        custom_name=payload.custom_name,
        dose=payload.dose,
        frequency_type=payload.frequency_type.value,
        days_of_week=days,
        times_of_day=payload.times_of_day,
        relation_to_food=payload.relation_to_food.value if payload.relation_to_food else None,
        notes=payload.notes,
    )
    session.add(med)
    await session.flush()
    await session.refresh(med)
    return med


async def update_medication(
    session: AsyncSession,
    medication_id: UUID,
    user_id: int,
    payload: schemas.MedicationUpdate,
    change_reason: str | None = None,
) -> Medication | None:
    med = await get_medication(session, medication_id, user_id)
    if med is None:
        return None
    # Save current state to history
    hist = MedicationHistory(
        medication_id=med.id,
        dose=med.dose,
        frequency_type=med.frequency_type,
        days_of_week=med.days_of_week,
        times_of_day=med.times_of_day,
        relation_to_food=med.relation_to_food,
        notes=med.notes,
        change_reason=change_reason or payload.change_reason,
    )
    session.add(hist)
    # Apply updates
    if payload.dose is not None:
        med.dose = payload.dose
    if payload.frequency_type is not None:
        med.frequency_type = payload.frequency_type.value
        if payload.frequency_type == FrequencyType.daily:
            med.days_of_week = None
    if payload.days_of_week is not None:
        med.days_of_week = payload.days_of_week
    if payload.times_of_day is not None:
        med.times_of_day = payload.times_of_day
    if payload.relation_to_food is not None:
        med.relation_to_food = payload.relation_to_food.value
    if payload.notes is not None:
        med.notes = payload.notes
    await session.flush()
    await session.refresh(med)
    return med


async def archive_medication(
    session: AsyncSession,
    medication_id: UUID,
    user_id: int,
) -> bool:
    med = await get_medication(session, medication_id, user_id)
    if med is None:
        return False
    from datetime import timezone
    med.is_active = False
    med.archived_at = datetime.now(timezone.utc)
    await session.flush()
    return True


# --- History ---


async def get_medication_history(
    session: AsyncSession,
    medication_id: UUID,
    user_id: int,
) -> Sequence[MedicationHistory]:
    med = await get_medication(session, medication_id, user_id)
    if med is None:
        return []
    stmt = (
        select(MedicationHistory)
        .where(MedicationHistory.medication_id == medication_id)
        .order_by(MedicationHistory.changed_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


# --- Schedule (on-the-fly) ---


async def get_schedule(
    session: AsyncSession,
    user_id: int,
    target_date: date,
) -> schemas.DayScheduleOut:
    settings = await get_or_create_settings(session, user_id)
    stmt = select(Medication).where(
        Medication.user_id == user_id,
        Medication.is_active.is_(True),
    )
    result = await session.execute(stmt)
    medications = result.scalars().all()
    day_of_week = target_date.weekday()  # 0=пн, 6=вс
    slots: list[schemas.ScheduleSlot] = []
    for med in medications:
        if med.frequency_type == FrequencyType.daily.value:
            takes_today = True
        else:
            takes_today = day_of_week in (med.days_of_week or [])
        if not takes_today:
            continue
        for t in med.times_of_day:
            intake_status = None
            taken_at = None
            if settings.tracking_enabled:
                intake = await find_intake(session, med.id, target_date, t)
                if intake:
                    intake_status = IntakeStatus(intake.status)
                    taken_at = intake.taken_at
            slot = schemas.ScheduleSlot(
                medication_id=med.id,
                medication_name=med.display_name,
                dose=med.dose,
                scheduled_time=t,
                relation_to_food=FoodRelation(med.relation_to_food) if med.relation_to_food else None,
                notes=med.notes,
                intake_status=intake_status,
                taken_at=taken_at,
            )
            slots.append(slot)
    groups = _group_slots_by_time(slots)
    return schemas.DayScheduleOut(
        date=target_date,
        day_of_week=day_of_week,
        day_name=get_day_name_ru(day_of_week),
        groups=groups,
        tracking_enabled=settings.tracking_enabled,
    )


def _group_slots_by_time(slots: list[schemas.ScheduleSlot]) -> list[schemas.ScheduleTimeGroup]:
    by_time: dict[time, list[schemas.ScheduleSlot]] = defaultdict(list)
    for slot in slots:
        by_time[slot.scheduled_time].append(slot)
    return [
        schemas.ScheduleTimeGroup(time=t, slots=sorted(sl, key=lambda s: s.medication_name))
        for t, sl in sorted(by_time.items())
    ]


async def find_intake(
    session: AsyncSession,
    medication_id: UUID,
    scheduled_date: date,
    scheduled_time: time,
) -> MedicationIntake | None:
    stmt = select(MedicationIntake).where(
        MedicationIntake.medication_id == medication_id,
        MedicationIntake.scheduled_date == scheduled_date,
        MedicationIntake.scheduled_time == scheduled_time,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# --- Settings ---


async def get_or_create_settings(
    session: AsyncSession,
    user_id: int,
) -> UserMedicationSettings:
    stmt = select(UserMedicationSettings).where(UserMedicationSettings.user_id == user_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    settings = UserMedicationSettings(user_id=user_id, tracking_enabled=True)
    session.add(settings)
    await session.flush()
    await session.refresh(settings)
    return settings


async def update_settings(
    session: AsyncSession,
    user_id: int,
    payload: schemas.MedicationSettingsUpdate,
) -> UserMedicationSettings:
    settings = await get_or_create_settings(session, user_id)
    settings.tracking_enabled = payload.tracking_enabled
    await session.flush()
    await session.refresh(settings)
    return settings


# --- Intake ---


async def upsert_intake(
    session: AsyncSession,
    user_id: int,
    payload: schemas.IntakeRecordCreate,
) -> MedicationIntake | None:
    med = await get_medication(session, payload.medication_id, user_id)
    if med is None or not med.is_active:
        return None
    taken_at = payload.taken_at
    if payload.status.value == "taken" and taken_at is None:
        from datetime import timezone
        taken_at = datetime.now(timezone.utc)
    existing = await find_intake(session, payload.medication_id, payload.scheduled_date, payload.scheduled_time)
    if existing:
        existing.status = payload.status.value
        existing.taken_at = taken_at
        await session.flush()
        await session.refresh(existing)
        return existing
    intake = MedicationIntake(
        medication_id=payload.medication_id,
        scheduled_date=payload.scheduled_date,
        scheduled_time=payload.scheduled_time,
        status=payload.status.value,
        taken_at=taken_at,
    )
    session.add(intake)
    await session.flush()
    await session.refresh(intake)
    return intake


async def list_intakes(
    session: AsyncSession,
    user_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
    medication_id: UUID | None = None,
    status: str | None = None,
) -> Sequence[MedicationIntake]:
    stmt = (
        select(MedicationIntake)
        .join(Medication, MedicationIntake.medication_id == Medication.id)
        .where(Medication.user_id == user_id)
    )
    if from_date is not None:
        stmt = stmt.where(MedicationIntake.scheduled_date >= from_date)
    if to_date is not None:
        stmt = stmt.where(MedicationIntake.scheduled_date <= to_date)
    if medication_id is not None:
        stmt = stmt.where(MedicationIntake.medication_id == medication_id)
    if status is not None:
        stmt = stmt.where(MedicationIntake.status == status)
    stmt = stmt.order_by(MedicationIntake.scheduled_date.desc(), MedicationIntake.scheduled_time.desc())
    result = await session.execute(stmt)
    return result.scalars().all()
