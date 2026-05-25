# ============================================
# Researchers CRUD: Управление пациентами исследователя
# ============================================
# Генерация номеров пациентов, создание аккаунтов с PIN,
# сброс PIN, список пациентов исследователя.

"""CRUD operations for researcher-managed patients."""

from __future__ import annotations

import logging
import secrets
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User
from app.researchers.models import Researcher
from app.auth.security import hash_pin, generate_pin, hash_password

logger = logging.getLogger("gpt-support-researcher")


# ---------------------------------------------------------------------------
# Patient number generation
# ---------------------------------------------------------------------------

async def _generate_unique_patient_number(session: AsyncSession) -> int:
    """Generate a unique 4-digit patient number (1000–9999)."""
    for _ in range(100):  # safety limit
        number = secrets.randbelow(9000) + 1000
        exists = await session.execute(
            select(User.id).where(User.patient_number == number)
        )
        if exists.scalar_one_or_none() is None:
            return number
    raise RuntimeError("Не удалось сгенерировать уникальный номер пациента")


# ---------------------------------------------------------------------------
# Patient CRUD
# ---------------------------------------------------------------------------

async def create_patient(
    session: AsyncSession,
    *,
    full_name: str,
    age: Optional[int] = None,
    gender: Optional[str] = None,
) -> tuple[User, str]:
    """Create a new patient with generated number and PIN.

    Returns ``(user, plaintext_pin)``.
    """
    patient_number = await _generate_unique_patient_number(session)
    pin = generate_pin(4)
    pin_hashed = hash_pin(pin)

    user = User(
        full_name=full_name,
        age=age,
        gender=gender,
        patient_number=patient_number,
        pin_hash=pin_hashed,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info(
        "[researcher] created patient id=%s, number=%s",
        user.id,
        patient_number,
    )
    return user, pin


async def list_patients(session: AsyncSession) -> Sequence[User]:
    """Return all patients ordered by id desc, with center, KDQOL points and schedules loaded."""
    from sqlalchemy.orm import selectinload
    result = await session.execute(
        select(User)
        .options(selectinload(User.center))
        .options(selectinload(User.measurement_points))
        .options(selectinload(User.dialysis_schedules))
        .order_by(User.id.desc())
    )
    return result.scalars().all()


async def update_patient_center(
    session: AsyncSession,
    user: User,
    center_id: Optional[UUID],
) -> User:
    """Assign or clear dialysis center for a patient."""
    user.center_id = center_id
    await session.commit()
    await session.refresh(user)
    return user


async def get_patient_by_id(
    session: AsyncSession,
    patient_id: int,
) -> Optional[User]:
    result = await session.execute(
        select(User).where(User.id == patient_id)
    )
    return result.scalar_one_or_none()


async def reset_patient_pin(
    session: AsyncSession,
    user: User,
) -> str:
    """Generate a new PIN for the patient. Returns plaintext PIN."""
    pin = generate_pin(4)
    user.pin_hash = hash_pin(pin)
    user.pin_attempts = 0
    user.is_locked = False
    await session.commit()
    await session.refresh(user)
    logger.info("[researcher] reset PIN for patient id=%s", user.id)
    return pin


async def unlock_patient(
    session: AsyncSession,
    user: User,
) -> User:
    """Unlock a locked patient account."""
    user.is_locked = False
    user.pin_attempts = 0
    await session.commit()
    await session.refresh(user)
    logger.info("[researcher] unlocked patient id=%s", user.id)
    return user


async def bulk_delete_patients(
    session: AsyncSession,
    patient_ids: list[int],
) -> int:
    """Hard-delete multiple patients by id. Returns count of deleted records.

    Manually cascades deletions for FK references that lack ON DELETE CASCADE.
    """
    from sqlalchemy import delete as sa_delete, text
    from app.vitals.models import BPMeasurement, PulseMeasurement, WeightMeasurement, WaterIntake
    from app.medications.models import MedicationIntake, MedicationPrescription
    from app.dialysis.models import DialysisSchedule
    from app.sleep_tracker.models import SleepRecord

    if not patient_ids:
        return 0

    # 1. Medication intakes (FK → prescriptions, so delete first)
    await session.execute(
        sa_delete(MedicationIntake).where(MedicationIntake.patient_id.in_(patient_ids))
    )
    # 2. Medication prescriptions
    await session.execute(
        sa_delete(MedicationPrescription).where(MedicationPrescription.patient_id.in_(patient_ids))
    )
    # 3. Vitals (use user_id column)
    for VitalsModel in (BPMeasurement, PulseMeasurement, WeightMeasurement, WaterIntake):
        await session.execute(
            sa_delete(VitalsModel).where(VitalsModel.user_id.in_(patient_ids))
        )
    # 4. Dialysis schedules
    await session.execute(
        sa_delete(DialysisSchedule).where(DialysisSchedule.patient_id.in_(patient_ids))
    )
    # 5. Sleep records
    await session.execute(
        sa_delete(SleepRecord).where(SleepRecord.patient_id.in_(patient_ids))
    )
    # 6. Public badge/notification/streak tables (raw SQL — no ORM model)
    for table in ("patient_badges", "patient_notifications", "patient_streaks"):
        await session.execute(
            text(f"DELETE FROM {table} WHERE patient_id = ANY(:pids)"),  # noqa: S608
            {"pids": patient_ids},
        )

    # 7. Delete users — CASCADE handles the rest (education, scales, routine, llm, etc.)
    result = await session.execute(
        sa_delete(User).where(User.id.in_(patient_ids))
    )
    await session.commit()
    deleted = result.rowcount
    logger.info("[researcher] bulk deleted %s patients: %s", deleted, patient_ids)
    return deleted


async def bulk_block_patients(
    session: AsyncSession,
    patient_ids: list[int],
) -> int:
    """Set is_locked=True for multiple patients by id. Returns count of updated records."""
    from sqlalchemy import update as sa_update
    result = await session.execute(
        sa_update(User)
        .where(User.id.in_(patient_ids))
        .values(is_locked=True)
    )
    await session.commit()
    updated = result.rowcount
    logger.info("[researcher] bulk blocked %s patients: %s", updated, patient_ids)
    return updated


# ---------------------------------------------------------------------------
# Researcher CRUD
# ---------------------------------------------------------------------------

async def get_researcher_by_username(
    session: AsyncSession,
    username: str,
) -> Optional[Researcher]:
    result = await session.execute(
        select(Researcher).where(Researcher.username == username)
    )
    return result.scalar_one_or_none()


async def create_researcher(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    full_name: Optional[str] = None,
) -> Researcher:
    """Create a new researcher account."""
    researcher = Researcher(
        username=username,
        password_hash=hash_password(password),
        full_name=full_name,
    )
    session.add(researcher)
    await session.commit()
    await session.refresh(researcher)
    logger.info("[researcher] created researcher id=%s, username=%s", researcher.id, username)
    return researcher


async def get_patients_stats(session: AsyncSession) -> dict:
    """Return basic patient statistics for the dashboard."""
    total = await session.execute(select(func.count(User.id)))
    locked = await session.execute(
        select(func.count(User.id)).where(User.is_locked == True)  # noqa: E712
    )
    consented = await session.execute(
        select(func.count(User.id)).where(User.consent_personal_data == True)  # noqa: E712
    )
    return {
        "total_patients": total.scalar_one(),
        "locked_patients": locked.scalar_one(),
        "consented_patients": consented.scalar_one(),
    }


async def get_usage_stats(session: AsyncSession) -> dict:
    """Return usage statistics for modules (vitals, scales, education, sleep, routine)."""
    from app.vitals.models import BPMeasurement, PulseMeasurement, WeightMeasurement, WaterIntake
    from app.scales.models import ScaleResult
    from app.education.models import LessonProgress, LessonTestResult, PracticeLog
    from app.sleep_tracker.models import SleepRecord
    from app.routine.models import BaselineRoutine, DailyPlan, DailyVerification

    async def _count(model, col=None):
        c = col or model.id
        r = await session.execute(select(func.count(c)))
        return r.scalar_one()

    async def _count_distinct(model, col):
        r = await session.execute(select(func.count(func.distinct(col))))
        return r.scalar_one()

    # Vitals
    vitals_bp = await _count(BPMeasurement)
    vitals_pulse = await _count(PulseMeasurement)
    vitals_weight = await _count(WeightMeasurement)
    vitals_water = await _count(WaterIntake)
    vitals_users = await _count_distinct(BPMeasurement, BPMeasurement.user_id)

    # Scales — по каждой шкале отдельно
    scales_group = await session.execute(
        select(
            ScaleResult.scale_code,
            func.count(ScaleResult.id).label("records"),
            func.count(func.distinct(ScaleResult.user_id)).label("unique_patients"),
        )
        .group_by(ScaleResult.scale_code)
    )
    scales_by_code = [
        {
            "scale_code": row.scale_code,
            "records": row.records,
            "unique_patients": row.unique_patients,
        }
        for row in scales_group.all()
    ]
    scales_total = sum(s["records"] for s in scales_by_code)
    scales_users = await _count_distinct(ScaleResult, ScaleResult.user_id)

    # Education
    education_progress = await _count(LessonProgress)
    education_tests = await _count(LessonTestResult)
    education_practices = await _count(PracticeLog)
    education_users = await _count_distinct(LessonProgress, LessonProgress.user_id)

    # Sleep
    sleep_records = await _count(SleepRecord)
    sleep_users = await _count_distinct(SleepRecord, SleepRecord.patient_id)

    # Routine
    routine_baselines = await _count(BaselineRoutine)
    routine_plans = await _count(DailyPlan)
    routine_verifications = await _count(DailyVerification)
    routine_users = await _count_distinct(DailyPlan, DailyPlan.patient_id)

    return {
        "vitals": {
            "bp_measurements": vitals_bp,
            "pulse_measurements": vitals_pulse,
            "weight_measurements": vitals_weight,
            "water_intake": vitals_water,
            "total": vitals_bp + vitals_pulse + vitals_weight + vitals_water,
            "unique_patients": vitals_users,
        },
        "scales": {
            "total_records": scales_total,
            "unique_patients": scales_users,
            "by_scale": scales_by_code,
        },
        "education": {
            "lesson_progress": education_progress,
            "test_results": education_tests,
            "practice_logs": education_practices,
            "unique_patients": education_users,
        },
        "sleep": {
            "records": sleep_records,
            "unique_patients": sleep_users,
        },
        "routine": {
            "baselines": routine_baselines,
            "plans": routine_plans,
            "verifications": routine_verifications,
            "unique_patients": routine_users,
        },
    }
