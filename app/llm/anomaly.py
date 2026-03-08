"""
Anomaly Detector — обнаружение аномалий витальных показателей.

check_anomalies(patient_id, db) -> list[AnomalyAlert]
  - Проверяет показатели за последние 24ч.
  - Пороги:
      АД систолическое > 160 → WARNING, > 180 → CRITICAL
      Пульс > 100 или < 50  → WARNING
      Прирост веса > 2 кг   → WARNING (последние 2 записи)
  - Не падает при отсутствии данных — возвращает пустой список.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("gpt-support-llm.anomaly")

Severity = Literal["WARNING", "CRITICAL"]


@dataclass
class AnomalyAlert:
    type: str         # "systolic_bp" | "pulse" | "weight_gain"
    value: float      # измеренное значение
    threshold: float  # пересечённый порог
    severity: Severity
    domain_hint: str  # подсказка домена для промпта


async def check_anomalies(patient_id: int, db: AsyncSession) -> list[AnomalyAlert]:
    """
    Проверяет последние показатели пациента на аномалии.
    Не падает при ошибках — логирует warning и продолжает.
    """
    alerts: list[AnomalyAlert] = []
    for check_fn, name in [
        (_check_bp, "bp"),
        (_check_pulse, "pulse"),
        (_check_weight, "weight"),
    ]:
        try:
            alerts.extend(await check_fn(patient_id, db))
        except Exception as exc:
            logger.warning(
                "[anomaly] %s check failed patient=%d: %s", name, patient_id, exc
            )
    return alerts


async def _check_bp(patient_id: int, db: AsyncSession) -> list[AnomalyAlert]:
    from app.vitals.models import BPMeasurement

    since = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(BPMeasurement)
        .where(
            BPMeasurement.user_id == patient_id,
            BPMeasurement.measured_at >= since,
        )
        .order_by(BPMeasurement.measured_at.desc())
        .limit(5)
    )
    for bp in result.scalars().all():
        if bp.systolic > 180:
            return [AnomalyAlert("systolic_bp", bp.systolic, 180, "CRITICAL", "vitals")]
        if bp.systolic > 160:
            return [AnomalyAlert("systolic_bp", bp.systolic, 160, "WARNING", "vitals")]
    return []


async def _check_pulse(patient_id: int, db: AsyncSession) -> list[AnomalyAlert]:
    from app.vitals.models import BPMeasurement, PulseMeasurement

    since = datetime.utcnow() - timedelta(hours=24)

    # Сначала — таблица pulse_measurements
    result = await db.execute(
        select(PulseMeasurement)
        .where(
            PulseMeasurement.user_id == patient_id,
            PulseMeasurement.measured_at >= since,
        )
        .order_by(PulseMeasurement.measured_at.desc())
        .limit(5)
    )
    for p in result.scalars().all():
        if p.bpm > 100 or p.bpm < 50:
            threshold = 100 if p.bpm > 100 else 50
            return [AnomalyAlert("pulse", p.bpm, threshold, "WARNING", "vitals")]

    # Fallback — поле pulse в bp_measurements
    result = await db.execute(
        select(BPMeasurement)
        .where(
            BPMeasurement.user_id == patient_id,
            BPMeasurement.measured_at >= since,
            BPMeasurement.pulse.is_not(None),
        )
        .order_by(BPMeasurement.measured_at.desc())
        .limit(5)
    )
    for bp in result.scalars().all():
        if bp.pulse is not None and (bp.pulse > 100 or bp.pulse < 50):
            threshold = 100 if bp.pulse > 100 else 50
            return [AnomalyAlert("pulse", bp.pulse, threshold, "WARNING", "vitals")]

    return []


async def _check_weight(patient_id: int, db: AsyncSession) -> list[AnomalyAlert]:
    from app.vitals.models import WeightMeasurement

    since = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(WeightMeasurement)
        .where(WeightMeasurement.user_id == patient_id)
        .order_by(WeightMeasurement.measured_at.desc())
        .limit(2)
    )
    records = result.scalars().all()

    if len(records) < 2:
        return []

    latest, previous = records[0], records[1]

    # Проверяем, что последняя запись сделана в течение 24ч
    latest_dt = latest.measured_at
    if hasattr(latest_dt, "tzinfo") and latest_dt.tzinfo is not None:
        latest_dt = latest_dt.replace(tzinfo=None)
    if latest_dt < since:
        return []

    # Предыдущая запись должна быть не старше 7 дней — иначе разница нерепрезентативна
    prev_dt = previous.measured_at
    if hasattr(prev_dt, "tzinfo") and prev_dt.tzinfo is not None:
        prev_dt = prev_dt.replace(tzinfo=None)
    if prev_dt < datetime.utcnow() - timedelta(days=7):
        return []

    gain = float(latest.weight) - float(previous.weight)
    if gain > 2.0:
        return [AnomalyAlert("weight_gain", round(gain, 2), 2.0, "WARNING", "self_care")]

    return []
