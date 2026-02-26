"""
Domain Scorer — расчёт числовых показателей состояния пациента по доменам.

Функции:
  calculate_domain_scores(patient_id, db) -> dict[str, float]
    Возвращает score 0.0-1.0 для каждого домена (0 = плохо, 1 = хорошо).
    При ошибке запроса — 0.5 (нейтрально).

  get_priority_domains(scores) -> list[str]
    Сортирует домены по score (худший первый).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("gpt-support-llm.domain_scorer")


# ---------------------------------------------------------------------------
# Отдельные скореры
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

    # day_control_score предполагается в диапазоне 0-100
    avg = sum(scores) / len(scores)
    return max(0.0, min(1.0, avg / 100))


# ---------------------------------------------------------------------------
# Основные функции
# ---------------------------------------------------------------------------


async def calculate_domain_scores(
    patient_id: int,
    db: AsyncSession,
) -> dict[str, float]:
    """
    Рассчитывает скоры 0.0-1.0 для каждого домена.
    0.0 = плохо, 1.0 = хорошо.
    При ошибке запроса домен получает 0.5 (нейтрально).

    Домены с источником данных:
      sleep, medication, vitals, emotion (TODO), routine

    Домены без источника данных (TODO):
      stress, social, motivation → 0.5
    """
    scorers = {
        "sleep": _score_sleep,
        "medication": _score_medication,
        "vitals": _score_vitals,
        "emotion": _score_emotion,
        "routine": _score_routine,
    }

    scores: dict[str, float] = {}
    for domain, fn in scorers.items():
        try:
            scores[domain] = await fn(patient_id, db)
        except Exception as exc:
            logger.warning("[domain_scorer] Домен '%s' упал: %s", domain, exc)
            scores[domain] = 0.5

    # TODO: нет источника данных для этих доменов
    for domain in ("stress", "social", "motivation"):
        scores[domain] = 0.5

    return scores


def get_priority_domains(scores: dict[str, float]) -> list[str]:
    """
    Сортирует домены по score (худший первый).
    Используется для приоритизации тем в промпте.
    """
    return sorted(scores.keys(), key=lambda d: scores[d])
