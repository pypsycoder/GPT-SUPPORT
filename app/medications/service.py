# ============================================
# Medications Service: Prescriptions & Intakes CRUD, adherence, validations
# ============================================

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.medications.models import MedicationIntake, MedicationPrescription


# --- Adherence Rate ---


def calculate_adherence_rate(
    prescription: MedicationPrescription,
    intakes: Sequence[MedicationIntake],
    period_days: int = 30,
) -> float:
    """
    Доля принятых доз за последние period_days дней.
    Ожидаемое = frequency_times_per_day × кол-во активных дней в периоде
    Фактическое = кол-во записей в intakes за этот период
    Возвращает float 0.0–1.0
    """
    today = date.today()
    start = max(prescription.start_date, today - timedelta(days=period_days))
    end = prescription.end_date or today

    days_active = max(0, (min(today, end) - start).days + 1)
    if days_active == 0:
        return 0.0

    expected = days_active * prescription.frequency_times_per_day
    if expected == 0:
        return 0.0

    cutoff = datetime.combine(start, time.min).replace(tzinfo=timezone.utc)
    actual = sum(1 for i in intakes if i.intake_datetime >= cutoff)

    return min(1.0, actual / expected)


# --- Prescriptions CRUD ---


async def list_prescriptions(
    session: AsyncSession,
    patient_id: int,
    status: str = "active",
) -> list[MedicationPrescription]:
    stmt = select(MedicationPrescription).where(
        MedicationPrescription.patient_id == patient_id
    )
    if status != "all":
        stmt = stmt.where(MedicationPrescription.status == status)
    stmt = stmt.order_by(MedicationPrescription.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_prescription(
    session: AsyncSession,
    prescription_id: int,
    patient_id: int,
) -> MedicationPrescription | None:
    stmt = select(MedicationPrescription).where(
        MedicationPrescription.id == prescription_id,
        MedicationPrescription.patient_id == patient_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_prescription(
    session: AsyncSession,
    patient_id: int,
    payload,
) -> MedicationPrescription:
    prescription = MedicationPrescription(
        patient_id=patient_id,
        medication_name=payload.medication_name,
        dose=payload.dose,
        dose_unit=payload.dose_unit,
        frequency_times_per_day=payload.frequency_times_per_day,
        intake_schedule=payload.intake_schedule,
        route=payload.route,
        start_date=payload.start_date,
        end_date=payload.end_date,
        indication=payload.indication,
        instructions=payload.instructions,
        status=payload.status,
        prescribed_by=payload.prescribed_by,
    )
    session.add(prescription)
    await session.flush()
    await session.refresh(prescription)
    return prescription


async def update_prescription(
    session: AsyncSession,
    prescription_id: int,
    patient_id: int,
    payload,
) -> MedicationPrescription | None:
    prescription = await get_prescription(session, prescription_id, patient_id)
    if prescription is None:
        return None

    prescription.medication_name = payload.medication_name
    prescription.dose = payload.dose
    prescription.dose_unit = payload.dose_unit
    prescription.frequency_times_per_day = payload.frequency_times_per_day
    prescription.intake_schedule = payload.intake_schedule
    prescription.route = payload.route
    prescription.start_date = payload.start_date
    prescription.end_date = payload.end_date
    prescription.indication = payload.indication
    prescription.instructions = payload.instructions
    prescription.status = payload.status

    await session.flush()
    await session.refresh(prescription)
    return prescription


async def delete_prescription(
    session: AsyncSession,
    prescription_id: int,
    patient_id: int,
) -> MedicationPrescription | None:
    prescription = await get_prescription(session, prescription_id, patient_id)
    if prescription is None:
        return None
    await session.delete(prescription)
    await session.flush()
    return prescription


# --- Intakes for a prescription (for adherence calc) ---


async def get_intakes_for_prescription(
    session: AsyncSession,
    prescription_id: int,
) -> list[MedicationIntake]:
    stmt = (
        select(MedicationIntake)
        .where(MedicationIntake.prescription_id == prescription_id)
        .order_by(MedicationIntake.intake_datetime.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# --- Intakes CRUD ---


async def list_intakes(
    session: AsyncSession,
    patient_id: int,
    prescription_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[MedicationIntake]:
    stmt = select(MedicationIntake).where(
        MedicationIntake.patient_id == patient_id
    )
    if prescription_id is not None:
        stmt = stmt.where(MedicationIntake.prescription_id == prescription_id)
    stmt = stmt.order_by(MedicationIntake.intake_datetime.desc())
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_intake(
    session: AsyncSession,
    intake_id: int,
    patient_id: int,
) -> MedicationIntake | None:
    stmt = select(MedicationIntake).where(
        MedicationIntake.id == intake_id,
        MedicationIntake.patient_id == patient_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def check_duplicate_intake(
    session: AsyncSession,
    prescription_id: int,
    intake_datetime: datetime,
    threshold_minutes: int = 5,
) -> bool:
    """Проверяет, есть ли приём для этого prescription_id с |diff| < threshold_minutes."""
    lower = intake_datetime - timedelta(minutes=threshold_minutes)
    upper = intake_datetime + timedelta(minutes=threshold_minutes)
    stmt = select(func.count()).select_from(MedicationIntake).where(
        MedicationIntake.prescription_id == prescription_id,
        MedicationIntake.intake_datetime >= lower,
        MedicationIntake.intake_datetime <= upper,
    )
    result = await session.execute(stmt)
    count = result.scalar_one()
    return count > 0


async def create_intake(
    session: AsyncSession,
    patient_id: int,
    payload,
) -> MedicationIntake:
    now = datetime.now(timezone.utc)

    # is_retrospective: если intake_datetime < now() - 30 мин
    is_retrospective = payload.intake_datetime < (now - timedelta(minutes=30))

    intake = MedicationIntake(
        prescription_id=payload.prescription_id,
        patient_id=patient_id,
        intake_datetime=payload.intake_datetime,
        actual_dose=payload.actual_dose,
        intake_slot=payload.intake_slot,
        notes=payload.notes,
        is_retrospective=is_retrospective,
    )
    session.add(intake)
    await session.flush()
    await session.refresh(intake)
    return intake


async def update_intake(
    session: AsyncSession,
    intake_id: int,
    patient_id: int,
    payload,
) -> MedicationIntake | None:
    intake = await get_intake(session, intake_id, patient_id)
    if intake is None:
        return None

    if payload.intake_datetime is not None:
        intake.intake_datetime = payload.intake_datetime
    if payload.actual_dose is not None:
        intake.actual_dose = payload.actual_dose
    if payload.intake_slot is not None:
        intake.intake_slot = payload.intake_slot
    if payload.notes is not None:
        intake.notes = payload.notes

    await session.flush()
    await session.refresh(intake)
    return intake


async def delete_intake(
    session: AsyncSession,
    intake_id: int,
    patient_id: int,
) -> MedicationIntake | None:
    intake = await get_intake(session, intake_id, patient_id)
    if intake is None:
        return None
    await session.delete(intake)
    await session.flush()
    return intake
