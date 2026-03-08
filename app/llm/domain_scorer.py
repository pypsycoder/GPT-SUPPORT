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


async def _score_sleep(patient_id: int, db: AsyncSession) -> float | None:
    """
    Скор сна: sleep.sleep_records (7 дней) + PSQI (30 дней).

    Комбинирование:
      - оба источника → 0.6 * sleep_records + 0.4 * PSQI
      - только sleep_records → формула по часам сна
      - только PSQI → 1 - total/21
      - нет данных → None
    """
    from app.sleep_tracker.models import SleepRecord

    # --- sleep_records score ---
    sleep_score: float | None = None
    try:
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
        hours_list = [r.tst_minutes / 60 for r in records if r.tst_minutes]
        if hours_list:
            avg_hours = sum(hours_list) / len(hours_list)
            if avg_hours < 5:
                s = 0.2
            elif avg_hours < 6:
                s = 0.5
            elif avg_hours < 7:
                s = 0.7
            else:
                s = 1.0
            mid = len(hours_list) // 2
            if mid > 0 and len(hours_list) > 2:
                first_half = sum(hours_list[:mid]) / mid
                second_half = sum(hours_list[mid:]) / (len(hours_list) - mid)
                if second_half - first_half < -0.5:
                    s -= 0.1
            sleep_score = max(0.0, min(1.0, s))
    except Exception as exc:
        logger.debug("[domain_scorer] sleep_records error: %s", exc)

    # --- PSQI score (свежесть 30 дней) ---
    psqi_score: float | None = None
    try:
        row = await db.execute(
            text("""
                SELECT (result_json->>'total_score')::numeric AS total
                FROM scales.scale_results
                WHERE user_id    = :pid
                  AND scale_code = 'PSQI'
                  AND measured_at > now() - interval '30 days'
                ORDER BY measured_at DESC
                LIMIT 1
            """),
            {"pid": patient_id},
        )
        rec = row.fetchone()
        if rec is not None and rec.total is not None:
            psqi_score = round(max(0.0, min(1.0, 1.0 - float(rec.total) / 21.0)), 3)
    except Exception as exc:
        logger.debug("[domain_scorer] PSQI error: %s", exc)

    # --- blend ---
    if sleep_score is not None and psqi_score is not None:
        score = round(0.6 * sleep_score + 0.4 * psqi_score, 3)
        source = "sleep_records+PSQI"
    elif sleep_score is not None:
        score = sleep_score
        source = "sleep_records"
    elif psqi_score is not None:
        score = psqi_score
        source = "PSQI"
    else:
        logger.debug("[domain_scorer] sleep score=None source=no_data")
        return None

    logger.debug("[domain_scorer] sleep score=%s source=%s", score, source)
    return score


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
    """Скор на основе последнего АД (систолическое + диастолическое, берём худший)."""
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
        sys_score = 0.1
    elif systolic > 160:
        sys_score = 0.4
    elif systolic > 140:
        sys_score = 0.7
    else:
        sys_score = 1.0

    diastolic = bp.diastolic
    if diastolic > 110:
        dia_score = 0.1
    elif diastolic > 100:
        dia_score = 0.4
    elif diastolic > 90:
        dia_score = 0.7
    else:
        dia_score = 1.0

    return min(sys_score, dia_score)


async def _score_emotion(patient_id: int, db: AsyncSession) -> float | None:
    """
    Эмоциональное состояние по HADS (30 дней).

    HADS-A (тревога): anxiety_score 0-21
    HADS-D (депрессия): depression_score 0-21
    score = 1 - ((anxiety + depression) / 42)
    Если только одна подшкала — score = 1 - (value / 21).
    Нет свежих данных → None.
    """
    try:
        row = await db.execute(
            text("""
                SELECT
                    (result_json->>'anxiety_score')::numeric    AS anxiety,
                    (result_json->>'depression_score')::numeric AS depression
                FROM scales.scale_results
                WHERE user_id    = :pid
                  AND scale_code = 'HADS'
                  AND measured_at > now() - interval '30 days'
                ORDER BY measured_at DESC
                LIMIT 1
            """),
            {"pid": patient_id},
        )
        rec = row.fetchone()
    except Exception as exc:
        logger.debug("[domain_scorer] HADS error: %s", exc)
        return None

    if rec is None:
        logger.debug("[domain_scorer] emotion score=None source=no_data")
        return None

    anxiety = rec.anxiety
    depression = rec.depression

    if anxiety is not None and depression is not None:
        score = round(max(0.0, min(1.0, 1.0 - (float(anxiety) + float(depression)) / 42.0)), 3)
        source = "HADS_A+D"
    elif anxiety is not None:
        score = round(max(0.0, min(1.0, 1.0 - float(anxiety) / 21.0)), 3)
        source = "HADS_A"
    elif depression is not None:
        score = round(max(0.0, min(1.0, 1.0 - float(depression) / 21.0)), 3)
        source = "HADS_D"
    else:
        logger.debug("[domain_scorer] emotion score=None source=no_data")
        return None

    logger.debug("[domain_scorer] emotion score=%s source=%s", score, source)
    return score


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
    Мотивация: routine (7 дней) + KOP-25A (30 дней).

    Комбинирование:
      - оба источника → (completion_rate + kop_score) / 2
      - только routine  → completion_rate * 0.6 + control_norm * 0.4
      - только KOP-25A  → kop_score
      - нет данных      → None
    """
    # --- routine ---
    completion_rate: float | None = None
    control_norm: float | None = None
    try:
        row = await db.execute(
            text("""
                SELECT
                    COUNT(*)               AS verified_days,
                    AVG(day_control_score) AS avg_control
                FROM routine.daily_verifications
                WHERE patient_id        = :pid
                  AND verification_date > now() - interval '7 days'
            """),
            {"pid": patient_id},
        )
        rec = row.fetchone()
        if rec is not None and rec.verified_days > 0:
            completion_rate = min(float(rec.verified_days) / 7.0, 1.0)
            if rec.avg_control is not None:
                control_norm = min(float(rec.avg_control) / MAX_DAY_CONTROL_SCORE, 1.0)
    except Exception as exc:
        logger.debug("[domain_scorer] routine error: %s", exc)

    # --- KOP-25A (total_score = PL, диапазон 0-100) ---
    kop_score: float | None = None
    try:
        row = await db.execute(
            text("""
                SELECT (result_json->>'total_score')::numeric AS pl
                FROM scales.scale_results
                WHERE user_id    = :pid
                  AND scale_code = 'KOP25A'
                  AND measured_at > now() - interval '30 days'
                ORDER BY measured_at DESC
                LIMIT 1
            """),
            {"pid": patient_id},
        )
        rec = row.fetchone()
        if rec is not None and rec.pl is not None:
            kop_score = round(max(0.0, min(1.0, float(rec.pl) / 100.0)), 3)
    except Exception as exc:
        logger.debug("[domain_scorer] KOP25A error: %s", exc)

    # --- blend ---
    if completion_rate is not None and kop_score is not None:
        score = round((completion_rate + kop_score) / 2.0, 3)
        source = "routine+KOP25A"
    elif completion_rate is not None:
        cn = control_norm if control_norm is not None else 0.0
        score = round(completion_rate * 0.6 + cn * 0.4, 3)
        source = "routine"
    elif kop_score is not None:
        score = kop_score
        source = "KOP25A"
    else:
        logger.debug("[domain_scorer] motivation score=None source=no_data")
        return None

    logger.debug("[domain_scorer] motivation score=%s source=%s", score, source)
    return score


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
      sleep (sleep_records+PSQI), medication, vitals, routine,
      emotion (HADS), stress (PSS-10), social (KDQOL-SF),
      motivation (routine+KOP-25A)
    """
    # Домены с гарантированным float (нет внешних шкал, всегда есть данные)
    legacy_scorers: dict[str, any] = {
        "medication":  _score_medication,
        "vitals":      _score_vitals,
        "routine":     _score_routine,
    }

    # Домены — могут вернуть None (нет свежих данных = нет приоритета)
    new_scorers: dict[str, any] = {
        "sleep":       _score_sleep,       # sleep_records + PSQI
        "emotion":     _score_emotion,     # HADS
        "stress":      _score_stress,      # PSS-10
        "social":      _score_social,      # KDQOL-SF
        "motivation":  _score_motivation,  # routine + KOP-25A
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

    