"""
Badge Service — выдача бейджей достижений.

Таблицы-источники:
  medications.medication_intakes  patient_id  intake_datetime
  sleep.sleep_records             patient_id  sleep_date (DATE)
  vitals.bp_measurements          user_id     measured_at
  practices.practice_completions  patient_id  completed_at

Таблицы достижений (public schema):
  patient_badges    (patient_id, badge_key, level, earned_at)
  patient_notifications (patient_id, type, icon, title, message, action_url, action_text)
  patient_streaks   (patient_id, tracker, current_streak, best_streak, last_action_date)
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.badge_definitions import BADGE_DEFINITIONS

logger = logging.getLogger("gpt-support")

# ─────────────────────────────────────────────────────────────────────────────
# Конфигурация трекеров
# ─────────────────────────────────────────────────────────────────────────────

_TRACKER_CFG: dict[str, tuple[str, str, str]] = {
    # tracker: (schema.table, date_column, patient_id_column)
    "medications": ("medications.medication_intakes",  "intake_datetime", "patient_id"),
    "sleep":       ("sleep.sleep_records",             "sleep_date",      "patient_id"),
    "vitals":      ("vitals.bp_measurements",          "measured_at",     "user_id"),
    "practices":   ("practices.practice_completions",  "completed_at",    "patient_id"),
}

_TRACKER_THRESHOLDS: dict[str, list[tuple[str, int, int]]] = {
    # tracker: [(badge_key, window_days, required_days)]
    "medications": [
        ("med_start",   1,  1),
        ("med_week",    7,  5),
        ("med_2weeks", 14, 10),
        ("med_3weeks", 21, 15),
        ("med_month",  30, 22),
    ],
    "sleep": [
        ("sleep_start",   1,  1),
        ("sleep_week",    7,  5),
        ("sleep_2weeks", 14, 10),
        ("sleep_3weeks", 21, 15),
        ("sleep_month",  30, 22),
    ],
    "vitals": [
        ("vitals_start",   1,  1),
        ("vitals_week",    7,  5),
        ("vitals_2weeks", 14, 10),
        ("vitals_3weeks", 21, 15),
        ("vitals_month",  30, 22),
    ],
    "practices": [
        ("practice_start",   1,  1),
        ("practice_week",    7,  5),
        ("practice_2weeks", 14, 10),
        ("practice_3weeks", 21, 15),
        ("practice_month",  30, 22),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Низкоуровневые хелперы
# ─────────────────────────────────────────────────────────────────────────────

async def count_active_days(
    patient_id: int,
    table: str,
    date_col: str,
    patient_col: str,
    window_days: int,
    session: AsyncSession,
) -> int:
    """Считает уникальные дни с активностью в скользящем окне window_days.

    FIX: используем DATE(date_col) в условиях WHERE, чтобы сравнивать
    дату с датой, а не timestamptz с CURRENT_DATE (который PostgreSQL
    кастует в полночь сегодня — 00:00:00+00 — исключая все сегодняшние
    записи, сделанные после полуночи).
    """
    result = await session.execute(
        text(f"""
            SELECT COUNT(DISTINCT DATE({date_col}))
            FROM {table}
            WHERE {patient_col} = :pid
              AND DATE({date_col}) >= CURRENT_DATE - INTERVAL '{window_days} days'
              AND DATE({date_col}) <= CURRENT_DATE
        """),
        {"pid": patient_id},
    )
    return result.scalar() or 0


async def award_badge_if_new(
    patient_id: int,
    badge_key: str,
    session: AsyncSession,
) -> bool:
    """
    Выдаёт бейдж если ещё не выдан.
    Возвращает True если выдан впервые.
    Не делает commit — коммит в router.
    """
    if badge_key not in BADGE_DEFINITIONS:
        logger.warning("award_badge_if_new: неизвестный badge_key=%s", badge_key)
        return False

    exists = await session.execute(
        text("""
            SELECT 1 FROM patient_badges
            WHERE patient_id = :pid AND badge_key = :key
        """),
        {"pid": patient_id, "key": badge_key},
    )
    if exists.scalar():
        return False

    defn = BADGE_DEFINITIONS[badge_key]
    await session.execute(
        text("""
            INSERT INTO patient_badges (patient_id, badge_key, level, earned_at)
            VALUES (:pid, :key, :level, NOW())
            ON CONFLICT DO NOTHING
        """),
        {"pid": patient_id, "key": badge_key, "level": defn["level"]},
    )

    # Уведомление
    await session.execute(
        text("""
            INSERT INTO patient_notifications
                (patient_id, type, icon, title, message, action_url, action_text)
            VALUES
                (:pid, 'badge_earned', :icon, 'Новое достижение',
                 :msg, '/patient/profile#achievements', 'Посмотреть')
        """),
        {
            "pid": patient_id,
            "icon": defn["icon"],
            "msg": f"{defn['name']} — {defn['desc']}",
        },
    )

    logger.info("Бейдж выдан: patient=%s badge=%s", patient_id, badge_key)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Проверки серийных трекеров
# ─────────────────────────────────────────────────────────────────────────────

async def check_tracker_badges(
    patient_id: int,
    tracker: str,
    session: AsyncSession,
) -> None:
    """
    Проверяет все серийные пороги для одного трекера.
    tracker: 'medications' | 'sleep' | 'vitals' | 'practices'
    """
    if tracker not in _TRACKER_CFG:
        return

    table, date_col, patient_col = _TRACKER_CFG[tracker]

    for badge_key, window, required in _TRACKER_THRESHOLDS[tracker]:
        days = await count_active_days(
            patient_id, table, date_col, patient_col, window, session
        )
        if days >= required:
            await award_badge_if_new(patient_id, badge_key, session)


# ─────────────────────────────────────────────────────────────────────────────
# Специальные проверки
# ─────────────────────────────────────────────────────────────────────────────

async def check_vitals_full_day(patient_id: int, session: AsyncSession) -> None:
    """
    Бейдж vitals_full: все 4 показателя (АД, Пульс, Вес, Вода) внесены сегодня.
    Витальные используют user_id (не patient_id).
    """
    result = await session.execute(
        text("""
            SELECT
                (SELECT COUNT(*) FROM vitals.bp_measurements
                 WHERE user_id = :uid AND DATE(measured_at) = CURRENT_DATE) > 0 AS has_bp,
                (SELECT COUNT(*) FROM vitals.pulse_measurements
                 WHERE user_id = :uid AND DATE(measured_at) = CURRENT_DATE) > 0 AS has_pulse,
                (SELECT COUNT(*) FROM vitals.weight_measurements
                 WHERE user_id = :uid AND DATE(measured_at) = CURRENT_DATE) > 0 AS has_weight,
                (SELECT COUNT(*) FROM vitals.water_intake
                 WHERE user_id = :uid AND DATE(measured_at) = CURRENT_DATE) > 0 AS has_water
        """),
        {"uid": patient_id},
    )
    row = result.fetchone()
    if row and all(row):
        await award_badge_if_new(patient_id, "vitals_full", session)


async def check_practice_count_badges(patient_id: int, session: AsyncSession) -> None:
    """
    Бейджи за количество разных практик: practice_5 (5 уникальных), practice_all (9 уникальных).
    """
    result = await session.execute(
        text("""
            SELECT COUNT(DISTINCT practice_id)
            FROM practices.practice_completions
            WHERE patient_id = :pid
        """),
        {"pid": patient_id},
    )
    distinct_count = result.scalar() or 0

    if distinct_count >= 5:
        await award_badge_if_new(patient_id, "practice_5", session)
    if distinct_count >= 9:
        await award_badge_if_new(patient_id, "practice_all", session)


async def check_education_badges(patient_id: int, session: AsyncSession) -> None:
    """
    Бейджи за прогресс обучения.
    Уроки используют user_id (не patient_id).
    """
    # Первый завершённый урок
    result = await session.execute(
        text("""
            SELECT COUNT(*) FROM education.lesson_progress
            WHERE user_id = :uid AND is_completed = TRUE
        """),
        {"uid": patient_id},
    )
    lessons_done = result.scalar() or 0

    if lessons_done >= 1:
        await award_badge_if_new(patient_id, "lesson_first", session)

    # Блок психологии (block_code = 'psychology')
    result = await session.execute(
        text("""
            SELECT COUNT(DISTINCT lp.lesson_id)
            FROM education.lesson_progress lp
            JOIN education.lessons l ON l.id = lp.lesson_id
            WHERE lp.user_id = :uid
              AND lp.is_completed = TRUE
              AND l.block_code = 'psychology'
        """),
        {"uid": patient_id},
    )
    psych_done = result.scalar() or 0
    if psych_done >= 9:
        await award_badge_if_new(patient_id, "psych_block", session)

    # Блок нефрологии (block_code = 'nephrology')
    result = await session.execute(
        text("""
            SELECT COUNT(DISTINCT lp.lesson_id)
            FROM education.lesson_progress lp
            JOIN education.lessons l ON l.id = lp.lesson_id
            WHERE lp.user_id = :uid
              AND lp.is_completed = TRUE
              AND l.block_code = 'nephrology'
        """),
        {"uid": patient_id},
    )
    nephro_done = result.scalar() or 0
    if nephro_done >= 9:
        await award_badge_if_new(patient_id, "nephro_block", session)

    if lessons_done >= 18:
        await award_badge_if_new(patient_id, "all_lessons", session)


async def check_scale_badges(patient_id: int, session: AsyncSession) -> None:
    """
    Бейджи за шкалы.
    ScaleResult использует user_id (не patient_id).
    """
    result = await session.execute(
        text("""
            SELECT COUNT(DISTINCT scale_code)
            FROM scales.scale_results
            WHERE user_id = :uid
        """),
        {"uid": patient_id},
    )
    scales_done = result.scalar() or 0

    if scales_done >= 1:
        await award_badge_if_new(patient_id, "scale_first", session)

    # T0: все точки измерения типа T0 завершены (completed_at IS NOT NULL)
    result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE point_type = 'T0') AS total_t0,
                COUNT(*) FILTER (WHERE point_type = 'T0' AND completed_at IS NOT NULL) AS done_t0
            FROM kdqol.measurement_points
            WHERE patient_id = :pid
        """),
        {"pid": patient_id},
    )
    row = result.fetchone()
    if row and row.total_t0 > 0 and row.total_t0 == row.done_t0:
        await award_badge_if_new(patient_id, "scale_t0", session)
