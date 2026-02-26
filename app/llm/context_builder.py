"""
Context Builder — сбор данных пациента из БД для передачи в LLM.

Функции:
  build_context(patient_id, db) -> dict
    Собирает все разделы. Если раздел упал — логирует warning, возвращает [].

  format_context_for_llm(context) -> str
    Превращает dict в читаемый текст для системного промпта.
    Пустые разделы пропускаются.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("gpt-support-llm.context_builder")


# ---------------------------------------------------------------------------
# Отдельные разделы
# ---------------------------------------------------------------------------


async def _get_recent_vitals(patient_id: int, db: AsyncSession) -> list[str]:
    """Последние 7 записей АД из vitals.bp_measurements."""
    from app.vitals.models import BPMeasurement

    since = datetime.utcnow() - timedelta(days=7)
    result = await db.execute(
        select(BPMeasurement)
        .where(
            BPMeasurement.user_id == patient_id,
            BPMeasurement.measured_at >= since,
        )
        .order_by(BPMeasurement.measured_at.desc())
        .limit(7)
    )
    records = result.scalars().all()

    lines = []
    for r in records:
        date_str = r.measured_at.strftime("%d.%m")
        lines.append(f"АД {r.systolic}/{r.diastolic} ({date_str})")
    return lines


async def _get_medication_adherence(patient_id: int, db: AsyncSession) -> list[str]:
    """% приёма лекарств за 7 дней из medication_intakes vs prescriptions."""
    from app.medications.models import MedicationIntake, MedicationPrescription

    since = datetime.utcnow() - timedelta(days=7)

    # Записанные приёмы за 7 дней
    result = await db.execute(
        select(func.count(MedicationIntake.id)).where(
            MedicationIntake.patient_id == patient_id,
            MedicationIntake.intake_datetime >= since,
        )
    )
    taken = result.scalar() or 0

    # Ожидаемые приёмы: активные назначения × 7 дней
    result = await db.execute(
        select(func.sum(MedicationPrescription.frequency_times_per_day)).where(
            MedicationPrescription.patient_id == patient_id,
            MedicationPrescription.status == "active",
        )
    )
    freq_sum = result.scalar() or 0
    expected = int(freq_sum) * 7

    if expected == 0:
        return []

    pct = min(100, round(taken / expected * 100))
    return [f"Приём лекарств: {pct}% за 7 дней ({taken} из {expected})"]


async def _get_sleep_summary(patient_id: int, db: AsyncSession) -> list[str]:
    """Среднее сна и тренд из sleep.sleep_records."""
    from app.sleep_tracker.models import SleepRecord

    since = (datetime.utcnow() - timedelta(days=7)).date()
    result = await db.execute(
        select(SleepRecord)
        .where(
            SleepRecord.patient_id == patient_id,
            SleepRecord.sleep_date >= since,
        )
        .order_by(SleepRecord.sleep_date.asc())
        .limit(7)
    )
    records = result.scalars().all()

    if not records:
        return []

    hours_list = [r.tst_minutes / 60 for r in records if r.tst_minutes]
    if not hours_list:
        return []

    avg_hours = round(sum(hours_list) / len(hours_list), 1)

    # Тренд: сравниваем первую и вторую половину
    mid = len(hours_list) // 2
    if mid > 0 and len(hours_list) > 2:
        first_half = sum(hours_list[:mid]) / mid
        second_half = sum(hours_list[mid:]) / (len(hours_list) - mid)
        diff = second_half - first_half
        if diff > 0.5:
            trend = "растёт"
        elif diff < -0.5:
            trend = "снижается"
        else:
            trend = "стабильно"
    else:
        trend = "стабильно"

    return [f"Сон: среднее {avg_hours}ч, тренд {trend}"]


async def _get_active_practices(patient_id: int, db: AsyncSession) -> list[str]:
    """
    TODO: таблица practice_assignments не реализована.
    В текущей схеме назначения практик пациенту не хранятся отдельно.
    Возвращаем пустой список.
    """
    return []


async def _get_last_scale_scores(patient_id: int, db: AsyncSession) -> list[str]:
    """Последние результаты каждой шкалы из scales.scale_results."""
    from app.scales.models import ScaleResult

    result = await db.execute(
        select(ScaleResult)
        .where(ScaleResult.user_id == patient_id)
        .order_by(ScaleResult.measured_at.desc())
        .limit(50)
    )
    records = result.scalars().all()

    # Берём последний результат по каждой шкале (дедупликация)
    seen: dict[str, ScaleResult] = {}
    for r in records:
        if r.scale_code not in seen:
            seen[r.scale_code] = r

    lines = []
    for scale_code, r in seen.items():
        date_str = r.measured_at.strftime("%d.%m")
        score = None
        if isinstance(r.result_json, dict):
            score = r.result_json.get("total_score") or r.result_json.get("score")
        if score is not None:
            lines.append(f"{scale_code}: {score} ({date_str})")
        else:
            lines.append(f"{scale_code}: ({date_str})")
    return lines


async def _get_chat_history(patient_id: int, db: AsyncSession) -> list[dict]:
    """Последние 5 сообщений из llm.chat_messages."""
    from app.models.llm import ChatMessage

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.patient_id == patient_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(5)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in messages]


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------


async def build_context(patient_id: int, db: AsyncSession) -> dict:
    """
    Собирает данные пациента из БД.
    Если раздел вызвал исключение — логирует warning и возвращает пустой список.

    Returns:
        dict с ключами: recent_vitals, medication_adherence, sleep_summary,
        active_practices, last_scale_scores, chat_history
    """
    sections: dict[str, any] = {
        "recent_vitals": _get_recent_vitals,
        "medication_adherence": _get_medication_adherence,
        "sleep_summary": _get_sleep_summary,
        "active_practices": _get_active_practices,
        "last_scale_scores": _get_last_scale_scores,
        "chat_history": _get_chat_history,
    }

    context: dict = {}
    for name, fn in sections.items():
        try:
            context[name] = await fn(patient_id, db)
        except Exception as exc:
            logger.warning("[context_builder] Раздел '%s' упал: %s", name, exc)
            context[name] = []

    return context


def format_context_for_llm(context: dict) -> str:
    """
    Превращает dict контекста в читаемый текст для системного промпта.
    Пустые разделы пропускаются.

    Returns:
        Строка вида "=== Данные пациента ===\\n..." или "" если нет данных.
    """
    labels = {
        "recent_vitals": "Витальные показатели",
        "medication_adherence": "Приём лекарств",
        "sleep_summary": "Сон",
        "active_practices": "Активные практики",
        "last_scale_scores": "Шкалы",
        # chat_history передаётся отдельно в messages — здесь не выводим
    }

    lines: list[str] = []
    for key, label in labels.items():
        values = context.get(key, [])
        if not values:
            continue
        value_str = ", ".join(str(v) for v in values)
        lines.append(f"{label}: {value_str}")

    if not lines:
        return ""

    return "=== Данные пациента ===\n" + "\n".join(lines)
