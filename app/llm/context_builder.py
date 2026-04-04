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
import time
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.errors import RetrievalError

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


async def _get_recent_weight(patient_id: int, db: AsyncSession) -> list[str]:
    """Последние 3 записи веса за 14 дней из vitals.weight_measurements."""
    from app.vitals.models import WeightMeasurement

    since = datetime.utcnow() - timedelta(days=14)
    result = await db.execute(
        select(WeightMeasurement)
        .where(
            WeightMeasurement.user_id == patient_id,
            WeightMeasurement.measured_at >= since,
        )
        .order_by(WeightMeasurement.measured_at.desc())
        .limit(3)
    )
    records = result.scalars().all()

    return [
        f"Вес: {float(r.weight)} кг ({r.measured_at.strftime('%d.%m')})"
        for r in records
    ]


async def _get_recent_water(patient_id: int, db: AsyncSession) -> list[str]:
    """Среднее потребление воды за 7 дней из vitals.water_intake."""
    from app.vitals.models import WaterIntake

    since = datetime.utcnow() - timedelta(days=7)
    result = await db.execute(
        select(func.avg(WaterIntake.volume_ml)).where(
            WaterIntake.user_id == patient_id,
            WaterIntake.measured_at >= since,
        )
    )
    avg_ml = result.scalar()

    if avg_ml is None:
        return []

    return [f"Вода: среднее {round(avg_ml)} мл/день за 7 дней"]


async def _get_routine_summary(patient_id: int, db: AsyncSession) -> list[str]:
    """Верификации рутины за 7 дней из routine.daily_verifications."""

    from app.routine.models import DailyVerification

    since = (datetime.utcnow() - timedelta(days=7)).date()
    result = await db.execute(
        select(DailyVerification).where(
            DailyVerification.patient_id == patient_id,
            DailyVerification.verification_date >= since,
        )
    )
    records = result.scalars().all()

    if not records:
        return []

    days_count = len(records)
    avg_score = round(sum(r.day_control_score for r in records) / days_count)
    return [f"Рутина: {days_count} из 7 дней, средний контроль {avg_score}%"]


async def _get_rag_context(
    patient_id: int, query: str, db: AsyncSession
) -> tuple[list[str], dict]:
    """
    RAG: найти образовательные модули, релевантные запросу пациента.

    Для прочитанных уроков — добавляет релевантный фрагмент.
    Для непрочитанных — предлагает ознакомиться.
    """
    from app.rag.retriever import retrieve_relevant_modules_with_meta

    retrieval_result = await retrieve_relevant_modules_with_meta(query, patient_id, db, top_k=2)
    modules = retrieval_result["modules"]
    lines = []
    for m in modules:
        if m["is_read"]:
            lines.append(
                f"Пациент читал урок «{m['title']}». "
                f"Релевантный фрагмент: {m['chunk'][:200]}"
            )
        else:
            lines.append(
                f"По теме «{m['title']}» есть урок — можешь предложить пациенту."
            )
    return lines, retrieval_result["meta"]


async def _get_practices_summary(patient_id: int, db: AsyncSession) -> list[str]:
    """Выполненные практики за 7 дней + доступные активные практики (limit 5)."""
    from app.practices.models import PracticeCompletion, StandalonePractice

    since = datetime.utcnow() - timedelta(days=7)

    result = await db.execute(
        select(func.count(PracticeCompletion.id)).where(
            PracticeCompletion.patient_id == patient_id,
            PracticeCompletion.completed_at >= since,
        )
    )
    completed_count = result.scalar() or 0

    result = await db.execute(
        select(StandalonePractice)
        .where(StandalonePractice.is_active == True)  # noqa: E712
        .limit(5)
    )
    practices = result.scalars().all()

    if completed_count == 0 and not practices:
        return []

    lines = []
    if completed_count > 0:
        lines.append(f"Практики выполнено за 7 дней: {completed_count}")
    if practices:
        items = ", ".join(
            f"{p.title} ({p.icf_domain})" if p.icf_domain else p.title
            for p in practices
        )
        lines.append(f"Доступные практики: {items}")
    return lines


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


async def build_context(
    patient_id: int, db: AsyncSession, query: str = ""
) -> dict:
    bundle = await build_context_bundle(patient_id, db, query=query)
    return bundle["context"]


async def build_context_bundle(
    patient_id: int, db: AsyncSession, query: str = ""
) -> dict:
    """
    Собирает данные пациента из БД.
    Если раздел вызвал исключение — логирует warning и возвращает пустой список.

    Args:
        patient_id: ID пациента
        db:         AsyncSession
        query:      текст запроса пользователя (для RAG; пропускается если пустой
                    или короче 15 символов)

    Returns:
        dict с ключами: recent_vitals, medication_adherence, sleep_summary,
        active_practices, last_scale_scores, chat_history, rag_context
    """
    sections: dict[str, any] = {
        "recent_vitals": _get_recent_vitals,
        "medication_adherence": _get_medication_adherence,
        "sleep_summary": _get_sleep_summary,
        "active_practices": _get_active_practices,
        "last_scale_scores": _get_last_scale_scores,
        "recent_weight": _get_recent_weight,
        "recent_water": _get_recent_water,
        "routine_summary": _get_routine_summary,
        "practices_summary": _get_practices_summary,
        "chat_history": _get_chat_history,
    }

    context: dict = {}
    diagnostics: dict[str, object] = {
        "patient_id": patient_id,
        "query_length": len(query),
        "total_latency_ms": 0,
        "sections_ok": [],
        "sections_failed": [],
        "section_latency_ms": {},
        "section_item_counts": {},
        "rag": {
            "attempted": False,
            "skipped_reason": None,
            "backend": None,
            "backend_selected": None,
            "candidate_rows": 0,
            "query_vector_dims": 0,
            "embedding_request_ms": 0,
            "vector_search_ms": 0,
            "progress_lookup_ms": 0,
            "pgvector_extension_installed": False,
            "pgvector_column_present": False,
            "pgvector_index_present": False,
            "pgvector_blocker": None,
            "invalid_embedding_rows": 0,
            "hit_count": 0,
            "error": None,
            "latency_ms": 0,
        },
    }

    total_started = time.monotonic()
    for name, fn in sections.items():
        started = time.monotonic()
        try:
            context[name] = await fn(patient_id, db)
            diagnostics["sections_ok"].append(name)
        except (SQLAlchemyError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            logger.warning("[context_builder] Раздел '%s' упал: %s", name, exc)
            context[name] = []
            diagnostics["sections_failed"].append(name)
        finally:
            diagnostics["section_latency_ms"][name] = int((time.monotonic() - started) * 1000)
            diagnostics["section_item_counts"][name] = len(context[name]) if isinstance(context[name], list) else 0

    # RAG: ищем релевантные образовательные модули только для содержательных запросов
    context["rag_context"] = []
    if len(query) > 15:
        rag_started = time.monotonic()
        diagnostics["rag"]["attempted"] = True
        try:
            context["rag_context"], rag_meta = await _get_rag_context(patient_id, query, db)
            diagnostics["rag"]["hit_count"] = len(context["rag_context"])
            diagnostics["rag"]["backend"] = rag_meta.get("backend")
            diagnostics["rag"]["backend_selected"] = rag_meta.get("backend_selected")
            diagnostics["rag"]["candidate_rows"] = rag_meta.get("candidate_rows", 0)
            diagnostics["rag"]["query_vector_dims"] = rag_meta.get("query_vector_dims", 0)
            diagnostics["rag"]["embedding_request_ms"] = rag_meta.get("embedding_request_ms", 0)
            diagnostics["rag"]["vector_search_ms"] = rag_meta.get("vector_search_ms", 0)
            diagnostics["rag"]["progress_lookup_ms"] = rag_meta.get("progress_lookup_ms", 0)
            diagnostics["rag"]["pgvector_extension_installed"] = rag_meta.get("pgvector_extension_installed", False)
            diagnostics["rag"]["pgvector_column_present"] = rag_meta.get("pgvector_column_present", False)
            diagnostics["rag"]["pgvector_index_present"] = rag_meta.get("pgvector_index_present", False)
            diagnostics["rag"]["pgvector_blocker"] = rag_meta.get("pgvector_blocker")
            diagnostics["rag"]["invalid_embedding_rows"] = rag_meta.get("invalid_embedding_rows", 0)
        except RetrievalError as exc:
            logger.warning("[context_builder] RAG retriever упал: %s", exc)
            diagnostics["rag"]["error"] = str(exc)
        finally:
            diagnostics["rag"]["latency_ms"] = int((time.monotonic() - rag_started) * 1000)
    else:
        diagnostics["rag"]["skipped_reason"] = "query_too_short"

    diagnostics["total_latency_ms"] = int((time.monotonic() - total_started) * 1000)

    return {"context": context, "diagnostics": diagnostics}


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
        "recent_weight": "Вес",
        "recent_water": "Потребление воды",
        "routine_summary": "Рутина",
        "practices_summary": "Практики",
        "rag_context": "Образовательные модули",
        # chat_history передаётся отдельно в messages — здесь не выводим
    }

    lines: list[str] = []
    for key, label in labels.items():
        values = context.get(key, [])
        if not values:
            continue
        # rag_context содержит полные предложения — выводим по одному на строку
        if key == "rag_context":
            lines.append(f"{label}:")
            for item in values:
                lines.append(f"  - {item}")
        else:
            value_str = ", ".join(str(v) for v in values)
            lines.append(f"{label}: {value_str}")

    if not lines:
        return ""

    return "=== Данные пациента ===\n" + "\n".join(lines)
