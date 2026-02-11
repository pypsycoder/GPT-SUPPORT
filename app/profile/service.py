# ============================================
# Profile Service: Агрегатор данных профиля пациента
# ============================================
# Собирает сводку профиля: витальные показатели, прогресс обучения,
# результаты шкал. Также обновление ФИО/возраста/пола.

"""Сервисный слой для профиля пациента."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.education.models import LessonProgress, LessonTestResult, PracticeLog
from app.profile.schemas import (
    DialysisSummary,
    EducationSummary,
    LastBP,
    LastPulse,
    LastScale,
    LastWeight,
    ProfileSummary,
    ProfileUpdate,
    ScalesSummary,
    VitalsSummary,
)
from app.dialysis.crud import get_active_schedule, get_center_by_id
from app.scales.models import ScaleResult
from app.scales.registry import SCALE_CALCULATORS
from app.users.models import User
from app.vitals.models import BPMeasurement, PulseMeasurement, WaterIntake, WeightMeasurement


# ============================================
#   Константы
# ============================================

SCALE_NAMES = {
    "HADS": "Госпитальная шкала тревоги и депрессии",
    "KOP_25A1": "КОП-25 (копинг-стратегии)",
    "KOP25A": "КОП-25 (копинг-стратегии)",
    "TOBOL": "ТОБОЛ (отношение к болезни)",
    "PSQI": "Питтсбургский опросник качества сна",
}


# ============================================
#   Сводка витальных показателей
# ============================================

async def _get_vitals_summary(session: AsyncSession, user_id: int) -> VitalsSummary:
    """Получает сводку по витальным показателям пациента."""

    # Последнее измерение АД
    bp_stmt = (
        select(BPMeasurement)
        .where(BPMeasurement.user_id == user_id)
        .order_by(BPMeasurement.measured_at.desc())
        .limit(1)
    )
    bp_result = await session.execute(bp_stmt)
    bp = bp_result.scalar_one_or_none()

    last_bp = None
    if bp:
        last_bp = LastBP(
            systolic=bp.systolic,
            diastolic=bp.diastolic,
            pulse=bp.pulse,
            measured_at=bp.measured_at,
        )

    # Последнее измерение пульса
    pulse_stmt = (
        select(PulseMeasurement)
        .where(PulseMeasurement.user_id == user_id)
        .order_by(PulseMeasurement.measured_at.desc())
        .limit(1)
    )
    pulse_result = await session.execute(pulse_stmt)
    pulse = pulse_result.scalar_one_or_none()

    last_pulse = None
    if pulse:
        last_pulse = LastPulse(
            bpm=pulse.bpm,
            measured_at=pulse.measured_at,
        )

    # Последнее измерение веса
    weight_stmt = (
        select(WeightMeasurement)
        .where(WeightMeasurement.user_id == user_id)
        .order_by(WeightMeasurement.measured_at.desc())
        .limit(1)
    )
    weight_result = await session.execute(weight_stmt)
    weight = weight_result.scalar_one_or_none()

    last_weight = None
    if weight:
        last_weight = LastWeight(
            weight=float(weight.weight),
            measured_at=weight.measured_at,
        )

    # Сумма воды за сегодня
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    water_stmt = (
        select(func.sum(WaterIntake.volume_ml))
        .where(WaterIntake.user_id == user_id)
        .where(WaterIntake.measured_at >= today_start)
    )
    water_result = await session.execute(water_stmt)
    water_today = water_result.scalar_one_or_none()

    return VitalsSummary(
        last_bp=last_bp,
        last_pulse=last_pulse,
        last_weight=last_weight,
        last_water_today_ml=int(water_today) if water_today else None,
    )


# ============================================
#   Сводка обучения
# ============================================

async def _get_education_summary(session: AsyncSession, user_id: int) -> EducationSummary:
    """Получает сводку по обучению пациента."""

    # Общее количество уроков (из прогресса пациента)
    lessons_stmt = (
        select(func.count(LessonProgress.id))
        .where(LessonProgress.user_id == user_id)
    )
    lessons_result = await session.execute(lessons_stmt)
    lessons_total = lessons_result.scalar_one() or 0

    # Завершенные уроки
    completed_stmt = (
        select(func.count(LessonProgress.id))
        .where(LessonProgress.user_id == user_id)
        .where(LessonProgress.is_completed == True)
    )
    completed_result = await session.execute(completed_stmt)
    lessons_completed = completed_result.scalar_one() or 0

    # Пройденные тесты
    tests_stmt = (
        select(func.count(LessonTestResult.id))
        .where(LessonTestResult.user_id == user_id)
        .where(LessonTestResult.passed == True)
    )
    tests_result = await session.execute(tests_stmt)
    tests_passed = tests_result.scalar_one() or 0

    # Выполненные практики (через user_id)
    practices_stmt = (
        select(func.count(PracticeLog.id))
        .where(PracticeLog.user_id == user_id)
    )
    practices_result = await session.execute(practices_stmt)
    practices_done = practices_result.scalar_one() or 0

    # Последняя активность - максимум из прогресса уроков и тестов
    last_progress_stmt = (
        select(func.max(LessonProgress.updated_at))
        .where(LessonProgress.user_id == user_id)
    )
    last_progress_result = await session.execute(last_progress_stmt)
    last_progress = last_progress_result.scalar_one()

    last_test_stmt = (
        select(func.max(LessonTestResult.created_at))
        .where(LessonTestResult.user_id == user_id)
    )
    last_test_result = await session.execute(last_test_stmt)
    last_test = last_test_result.scalar_one()

    if last_progress and last_test:
        last_activity_at = max(last_progress, last_test)
    else:
        last_activity_at = last_progress or last_test

    return EducationSummary(
        lessons_total=lessons_total,
        lessons_completed=lessons_completed,
        tests_passed=tests_passed,
        practices_done=practices_done,
        last_activity_at=last_activity_at,
    )


# ============================================
#   Сводка шкал
# ============================================

async def _get_scales_summary(session: AsyncSession, user_id: int) -> ScalesSummary:
    """Получает сводку по психологическим шкалам пациента."""

    # Количество пройденных шкал (уникальные scale_code)
    passed_stmt = (
        select(func.count(func.distinct(ScaleResult.scale_code)))
        .where(ScaleResult.user_id == user_id)
    )
    passed_result = await session.execute(passed_stmt)
    scales_passed = passed_result.scalar_one() or 0

    # Количество доступных шкал
    scales_available = len(SCALE_CALCULATORS)

    # Последняя пройденная шкала
    last_stmt = (
        select(ScaleResult)
        .where(ScaleResult.user_id == user_id)
        .order_by(ScaleResult.measured_at.desc())
        .limit(1)
    )
    last_result = await session.execute(last_stmt)
    last_scale_row = last_result.scalar_one_or_none()

    last_scale = None
    if last_scale_row:
        scale_code = last_scale_row.scale_code
        last_scale = LastScale(
            code=scale_code,
            name=SCALE_NAMES.get(scale_code, scale_code),
            measured_at=last_scale_row.measured_at,
        )

    return ScalesSummary(
        scales_passed=scales_passed,
        scales_available=scales_available,
        last_scale=last_scale,
    )


# ============================================
#   Сводка диализа
# ============================================

async def _get_dialysis_summary(
    session: AsyncSession,
    user: User,
) -> Optional[DialysisSummary]:
    """Получает данные о диализном центре и расписании пациента."""

    center = None
    if user.center_id:
        center = await get_center_by_id(session, user.center_id)

    schedule = await get_active_schedule(session, user.id)

    if not center and not schedule:
        return None

    center_name = center.name if center else "—"
    center_city = center.city if center else None

    if schedule:
        return DialysisSummary(
            center_name=center_name,
            center_city=center_city,
            shift=schedule.shift,
            weekdays=schedule.weekdays,
        )

    if center:
        return DialysisSummary(
            center_name=center_name,
            center_city=center_city,
            shift="",
            weekdays=[],
        )

    return None


# ============================================
#   Профиль: сборка и обновление
# ============================================

async def get_profile_summary(
    session: AsyncSession,
    user: User,
) -> ProfileSummary:
    """Собирает все данные профиля пациента одним запросом."""

    vitals = await _get_vitals_summary(session, user.id)
    education = await _get_education_summary(session, user.id)
    scales = await _get_scales_summary(session, user.id)
    dialysis = await _get_dialysis_summary(session, user)

    return ProfileSummary(
        id=user.id,
        full_name=user.full_name,
        age=user.age,
        gender=user.gender,
        telegram_id=user.telegram_id,
        consent_personal_data=user.consent_personal_data,
        consent_bot_use=user.consent_bot_use,
        vitals=vitals,
        education=education,
        scales=scales,
        dialysis=dialysis,
    )


async def update_profile(
    session: AsyncSession,
    user: User,
    data: ProfileUpdate,
) -> User:
    """Обновляет профиль пациента (ФИО, возраст, пол)."""

    updated = False

    if data.full_name is not None and user.full_name != data.full_name:
        user.full_name = data.full_name
        updated = True

    if data.age is not None and user.age != data.age:
        user.age = data.age
        updated = True

    if data.gender is not None and user.gender != data.gender:
        user.gender = data.gender
        updated = True

    if updated:
        await session.commit()
        await session.refresh(user)

    return user
