"""
Domain Scorer — расчёт числовых показателей состояния пациента по доменам.

Функции:
  calculate_domain_scores(patient_id, db) -> dict[str, float | None]
    Возвращает score 0.0-1.0 для каждого домена (0 = плохо, 1 = хорошо).
    None = нет свежих данных (честнее чем 0.5).
    При ошибке запроса — 0.5 (нейтрально, fallback).

  get_priority_domains(scores) -> list[str]
    Сортирует домены по score (худший первый).
    Домены с None помещаются в конец (нет данных = нет приоритета).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("gpt-support-llm.domain_scorer")

# Шкалы старше этого порога не используются
FRESHNESS_DAYS = 30

# Теоретический максимум day_control_score (подтверждён по коду фронта)
MAX_DAY_CONTROL_SCORE = 100


# ---------------------------------------------------------------------------
# Скореры — реализованные домены
# ---------------------------------------------------------------------------


async def _score_sleep(patient_id: int, db: AsyncSession) -> float:
    """Скор сна на основе sleep.sleep_records за 7 дней."""
    from app.sleep_tracker.models import SleepRecord

    since = (datetime.utcnow() - timedelta(days=7)).date()
    result = await db.execute(
        select(SleepRecord)
        .where(
            SleepRecord.patient_id == patient_id,
            SleepRecord.sleep_date >= since,
        )
        .order_by(SleepRecord.sleep_date.asc())
    )
    records = result.scalars().all()

    if not records:
        return 0.5

    hours_list = [r.tst_minutes / 60 for r in records if r.tst_minutes]
    if not hours_list:
        return 0.5

    avg_hours = sum(hours_list) / len(hours_list)

    if avg_hours < 5:
        score = 0.2
    elif avg_hours < 6:
        score = 0.5
    elif avg_hours < 7:
        score = 0.7
    else:
        score = 1.0

    # Штраф за снижающийся тренд
    mid = len(hours_list) // 2
    if mid > 0 and len(hours_list) > 2:
        first_half = sum(hours_list[:mid]) / mid
        second_half = sum(hours_list[mid:]) / (len(hours_list) - mid)
        if second_half - first_half < -0.5:
            score -= 0.1

    return max(0.0, min(1.0, score))


async def _score_medication(patient_id: int, db: AsyncSession) -> float:
    """Скор приёма лекарств: принято / ожидаемо за 7 дней."""
    from app.medications.models import MedicationIntake, MedicationPrescription

    since = datetime.utcnow() - timedelta(days=7)

    result = await db.execute(
        select(func.count(MedicationIntake.id)).where(
            MedicationIntake.patient_id == patient_id,
            MedicationIntake.intake_datetime >= since,
        )
    )
    taken = result.scalar() or 0

    result = await db.execute(
        select(func.sum(MedicationPrescription.frequency_times_per_day)).where(
            MedicationPrescription.patient_id == patient_id,
            MedicationPrescription.status == "active",
        )
    )
    freq_sum = result.scalar() or 0
    expected = int(freq_sum) * 7

    if expected == 0:
        return 0.5

    return max(0.0, min(1.0, taken / expected))


async def _score_vitals(patient_id: int, db: AsyncSession) -> float:
    """Скор на основе последнего систолического АД."""
    from app.vitals.models import BPMeasurement

    result = await db.execute(
        select(BPMeasurement)
        .where(BPMeasurement.user_id == patient_id)
        .order_by(BPMeasurement.measured_at.desc())
        .limit(1)
    )
    bp = result.scalar_one_or_none()

    if bp is None:
        return 0.5

    systolic = bp.systolic
    if systolic > 180:
        return 0.1
    elif systolic > 160:
        return 0.4
    elif systolic > 140:
        return 0.7
    else:
        return 1.0


async def _score_emotion(patient_id: int, db: AsyncSession) -> float:
    """
    TODO: таблица mood_logs не реализована.
    Возвращает нейтральный скор 0.5.
    """
    return 0.5


async def _score_routine(patient_id: int, db: AsyncSession) -> float:
    """Скор выполнения рутины по routine.daily_verifications за 7 дней."""
    from app.routine.models import DailyVerification

    since = (datetime.utcnow() - timedelta(days=7)).date()
    result = await db.execute(
        select(DailyVerification)
        .where(
            DailyVerification.patient_id == patient_id,
            DailyVerification.verification_date >= since,
        )
        .limit(7)
    )
    records = result.scalars().all()

    if not records:
        return 0.5

    scores = [
        r.day_control_score
        for r in records
        if r.day_control_score is not None
    ]
    if not scores:
        return 0.5

    avg = sum(scores) / len(scores)
    return max(0.0, min(1.0, avg / MAX_DAY_CONTROL_SCORE))


# ---------------------------------------------------------------------------
# Скореры — новые домены (stress / social / motivation)
# ---------------------------------------------------------------------------


async def _score_stress(patient_id: int, db: AsyncSession) -> float | None:
    """
    Стресс по PSS-10 (шкала 0-40, высокий балл = высокий стресс).
    score = 1 - (total / 40), т.е. 1.0 = нет стресса, 0.0 = максимальный.
    Данные старше FRESHNESS_DAYS дней не используются → None.
    """
    row = await db.execute(
        text("""
            SELECT (result_json->>'total_score')::numeric AS total
            FROM scales.scale_results
            WHERE user_id        = :pid
              AND scale_code     = 'PSS10'
              AND measured_at    > now() - interval '30 days'
            ORDER BY measured_at DESC
            LIMIT 1
        """),
        {"pid": patient_id},
    )
    rec = row.fetchone()

    if rec is None or rec.total is None:
        return None

    return round(max(0.0, min(1.0, 1.0 - float(rec.total) / 40.0)), 3)


async def _score_social(patient_id: int, db: AsyncSession) -> float | None:
    """
    Социальное функционирование по трём подшкалам KDQOL-SF (диапазон 0-100):
      - social_functioning
      - quality_social_interaction
      - social_support
    Берём последний measurement_point пациента (completed_at IS NOT NULL).
    None если опросник не заполнен или нет свежих данных.
    """
    row = await db.execute(
        text("""
            SELECT AVG(s.score) AS avg_score
            FROM kdqol.kdqol_subscale_scores s
            JOIN kdqol.measurement_points mp
              ON s.measurement_point_id = mp.id
            WHERE s.patient_id   = :pid
              AND s.subscale_name IN (
                  'social_functioning',
                  'quality_social_interaction',
                  'social_support'
              )
              AND mp.completed_at > now() - interval '30 days'
        """),
        {"pid": patient_id},
    )
    rec = row.fetchone()

    if rec is None or rec.avg_score is None:
        return None

    return round(max(0.0, min(1.0, float(rec.avg_score) / 100.0)), 3)


async def _score_motivation(patient_id: int, db: AsyncSession) -> float | None:
    """
    Мотивация через рутину за 7 дней.
    Компоненты:
      - completion_rate: кол-во дней с верификацией / 7  (вес 60%)
      - control_norm:   средний day_control_score / 100  (вес 40%)
    None если верификаций за 7 дней нет совсем
    (нет данных ≠ низкая мотивация).
    """
    row = await db.execute(
        text("""
            SELECT
                COUNT(*)                  AS verified_days,
                AVG(day_control_score)    AS avg_control
            FROM routine.daily_verifications
            WHERE patient_id        = :pid
              AND verification_date > now() - interval '7 days'
        """),
        {"pid": patient_id},
    )
    rec = row.fetchone()

    if rec is None or rec.verified_days == 0:
        return None

    completion_rate = min(float(rec.verified_days) / 7.0, 1.0)
    control_norm = min(float(rec.avg_control) / MAX_DAY_CONTROL_SCORE, 1.0)

    return round(completion_rate * 0.6 + control_norm * 0.4, 3)


# ---------------------------------------------------------------------------
# Основные функции
# ---------------------------------------------------------------------------


async def calculate_domain_scores(
    patient_id: int,
    db: AsyncSession,
) -> dict[str, float | None]:
    """
    Рассчитывает скоры для каждого домена.

    Возвращаемые значения:
      0.0-1.0  — есть данные, score рассчитан
      None     — нет свежих данных (агент должен это учитывать)
      0.5      — fallback при Exception (нейтрально, не блокирует)

    Домены:
      sleep, medication, vitals, emotion (stub), routine,
      stress (PSS-10), social (KDQOL-SF), motivation (routine logs)
    """
    # Домены с гарантированным float (legacy, оставляем как есть)
    legacy_scorers: dict[str, any] = {
        "sleep":       _score_sleep,
        "medication":  _score_medication,
        "vitals":      _score_vitals,
        "emotion":     _score_emotion,
        "routine":     _score_routine,
    }

    # Новые домены — могут вернуть None
    new_scorers: dict[str, any] = {
        "stress":      _score_stress,
        "social":      _score_social,
        "motivation":  _score_motivation,
    }

    scores: dict[str, float | None] = {}


    for domain, fn in {**legacy_scorers, **new_scorers}.items():
        try:
            scores[domain] = await fn(patient_id, db)
        except Exception as exc:
            logger.warning("[domain_scorer] Домен '%s' упал: %s", domain, exc)
            scores[domain] = 0.5  # fallback только при Exception

    return scores

def get_priority_domains(scores: dict[str, float | None]) -> list[str]:
    """
    Сортирует домены по score (худший первый).
    Домены с None помещаются в конец — нет данных, нет приоритета.
    """
    def sort_key(domain: str) -> float:
        v = scores[domain]
        return v if v is not None else 1.0  # None → в конец

    return sorted(scores.keys(), key=sort_key)

    