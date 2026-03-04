# ============================================
# Profile Service: Агрегатор данных профиля пациента
# ============================================
# Собирает сводку профиля: витальные показатели, прогресс обучения,
# результаты шкал. Также обновление ФИО/возраста/пола.

"""Сервисный слой для профиля пациента."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.education.models import LessonProgress, LessonTestResult, PracticeLog
from app.profile.schemas import (
    AchievementsProgress,
    AchievementsSummary,
    BadgeRead,
    DialysisSummary,
    EducationSummary,
    LastBP,
    LastPulse,
    LastScale,
    LastWeight,
    ProfileSummary,
    ProfileUpdate,
    ScalesSummary,
    StreakInfo,
    VitalsSummary,
)
from app.dialysis.crud import get_active_schedule, get_center_by_id
from app.notifications.badge_definitions import BADGE_DEFINITIONS
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
    "PSQI": "Питтсбургский опросник качества сна",
}


# ============================================
#   Подсчёт серий активности (fallback)
# ============================================

_TRACKER_ACTIVITY_CFG: dict[str, tuple[str, str, str]] = {
    # tracker: (schema.table, date_column, id_column)
    "medications": ("medications.medication_intakes", "intake_datetime", "patient_id"),
    "sleep": ("sleep.sleep_records", "sleep_date", "patient_id"),
    "vitals": ("vitals.bp_measurements", "measured_at", "user_id"),
    "practices": ("practices.practice_completions", "completed_at", "patient_id"),
}


async def _get_tracker_activity_dates(
    session: AsyncSession,
    user_id: int,
    tracker: str,
) -> list[date]:
    """Возвращает отсортированный список уникальных дат активности трекера."""
    cfg = _TRACKER_ACTIVITY_CFG.get(tracker)
    if not cfg:
        return []

    table, date_col, id_col = cfg
    result = await session.execute(
        text(
            f"""
            SELECT DISTINCT DATE({date_col}) AS d
            FROM {table}
            WHERE {id_col} = :uid
            ORDER BY DATE({date_col}) ASC
            """
        ),
        {"uid": user_id},
    )
    rows = result.fetchall()
    return [row[0] for row in rows if row[0] is not None]


def _compute_streak_from_dates(dates: list[date]) -> tuple[int, int]:
    """Считает текущую и лучшую серию по списку дат."""
    if not dates:
        return 0, 0

    # На всякий случай убираем дубликаты и сортируем
    unique_dates = sorted(set(dates))

    # Лучшая серия (max подряд)
    best = 1
    run = 1
    for i in range(1, len(unique_dates)):
        if (unique_dates[i] - unique_dates[i - 1]).days == 1:
            run += 1
        else:
            if run > best:
                best = run
            run = 1
    if run > best:
        best = run

    # Текущая серия — подряд идущие дни, заканчивающиеся последней датой
    current = 1
    for i in range(len(unique_dates) - 2, -1, -1):
        if (unique_dates[i + 1] - unique_dates[i]).days == 1:
            current += 1
        else:
            break

    return current, best


async def _fallback_tracker_streak(
    session: AsyncSession,
    user_id: int,
    tracker: str,
) -> StreakInfo:
    """Фолбэк: вычисляет серию по сырым данным, если в patient_streaks нет значений."""
    dates = await _get_tracker_activity_dates(session, user_id, tracker)
    current, best = _compute_streak_from_dates(dates)
    return StreakInfo(current=current, best=best)


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


async def get_achievements_summary(
    session: AsyncSession,
    user: User,
) -> AchievementsSummary:
    """Возвращает выданные бейджи, серии и прогресс пациента."""
    # ── Бейджи ────────────────────────────────────────────────────────────────
    rows = await session.execute(
        text("""
            SELECT badge_key, level, earned_at
            FROM patient_badges
            WHERE patient_id = :pid
            ORDER BY earned_at ASC
        """),
        {"pid": user.id},
    )
    badges: list[BadgeRead] = []
    for row in rows:
        defn = BADGE_DEFINITIONS.get(row.badge_key)
        if not defn:
            continue
        badges.append(BadgeRead(
            key=row.badge_key,
            icon=defn["icon"],
            color=defn["color"],
            level=row.level,
            name=defn["name"],
            desc=defn["desc"],
            tracker=defn["tracker"],
            earned_at=row.earned_at,
        ))

    # ── Серии ─────────────────────────────────────────────────────────────────
    rows = await session.execute(
        text("""
            SELECT tracker, current_streak, best_streak
            FROM patient_streaks
            WHERE patient_id = :pid
        """),
        {"pid": user.id},
    )
    streaks: dict[str, StreakInfo] = {}
    for row in rows:
        streaks[row.tracker] = StreakInfo(
            current=row.current_streak,
            best=row.best_streak,
        )
    # Если по какому-то трекеру серии нет или она вся из нулей — считаем по фактической активности
    for tracker in ("medications", "sleep", "vitals", "practices"):
        s = streaks.get(tracker)
        if s is None or (s.current == 0 and s.best == 0):
            streaks[tracker] = await _fallback_tracker_streak(session, user.id, tracker)

    # ── Прогресс ──────────────────────────────────────────────────────────────
    r = await session.execute(
        text("""
            SELECT COUNT(*) FROM education.lesson_progress
            WHERE user_id = :uid AND is_completed = TRUE
        """),
        {"uid": user.id},
    )
    lessons_done = r.scalar() or 0

    r = await session.execute(
        text("SELECT COUNT(*) FROM education.lessons WHERE is_active = TRUE"),
    )
    lessons_total = r.scalar() or 0

    r = await session.execute(
        text("""
            SELECT COUNT(DISTINCT scale_code) FROM scales.scale_results
            WHERE user_id = :uid
        """),
        {"uid": user.id},
    )
    scales_done = r.scalar() or 0

    r = await session.execute(
        text("""
            SELECT COUNT(DISTINCT practice_id) FROM practices.practice_completions
            WHERE patient_id = :pid
        """),
        {"pid": user.id},
    )
    practices_done = r.scalar() or 0

    r = await session.execute(
        text("SELECT COUNT(*) FROM practices.practices WHERE is_active = TRUE"),
    )
    practices_total = r.scalar() or 0

    progress = AchievementsProgress(
        lessons_done=lessons_done,
        lessons_total=lessons_total,
        scales_done=scales_done,
        practices_done=practices_done,
        practices_total=practices_total,
    )

    # ── Уровни трекеров (из уже загруженных бейджей) ──────────────────────────
    _badge_chains: dict[str, list[str]] = {
        "medications": ["med_start", "med_week", "med_2weeks", "med_3weeks", "med_month"],
        "sleep":       ["sleep_start", "sleep_week", "sleep_2weeks", "sleep_3weeks", "sleep_month"],
        "vitals":      ["vitals_start", "vitals_week", "vitals_2weeks", "vitals_3weeks", "vitals_month"],
        "practices":   ["practice_start", "practice_week", "practice_2weeks", "practice_3weeks", "practice_month"],
    }
    earned_keys = {b.key for b in badges}
    tracker_levels: dict[str, int] = {}
    for tracker, chain in _badge_chains.items():
        level = 0
        for i, key in enumerate(chain):
            if key in earned_keys:
                level = i + 1
        tracker_levels[tracker] = level

    # ── Уровень шкал T0/T1/T2 ─────────────────────────────────────────────────
    if "scale_t2" in earned_keys:
        scales_level = 3
    elif "scale_t1" in earned_keys:
        scales_level = 2
    elif "scale_t0" in earned_keys:
        scales_level = 1
    else:
        scales_level = 0

    return AchievementsSummary(
        badges=badges,
        streaks=streaks,
        progress=progress,
        tracker_levels=tracker_levels,
        scales_level=scales_level,
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
