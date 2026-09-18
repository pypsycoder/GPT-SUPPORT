# ============================================
# Researchers Service: Фаза 5 Track A
# ============================================
# Статистика/экспорт трекеров и шкал для исследователя — read-only выборки
# и агрегации поверх существующих данных пациентов. Ничего не пишет в БД.
# См. docs/agent/PHASE5_RESEARCH_INSTRUMENTATION_SPEC.md.

from __future__ import annotations

import csv
import io
import json as json_module
from datetime import date, datetime, time as dt_time
from typing import Any, Optional

from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.education.models import LessonTest, LessonTestResult
from app.scales.models import ScaleItemResponse
from app.sleep_tracker.models import SleepRecord
from app.vitals.models import BPMeasurement, PulseMeasurement, WaterIntake, WeightMeasurement


def _date_bounds(
    date_from: Optional[date], date_to: Optional[date]
) -> tuple[Optional[datetime], Optional[datetime]]:
    dt_from = datetime.combine(date_from, dt_time.min) if date_from else None
    dt_to = datetime.combine(date_to, dt_time.max) if date_to else None
    return dt_from, dt_to


# ---------------------------------------------------------------------------
# Шкалы — ответы по отдельным вопросам (HADS/KOP-25A/PSQI/PSS-10/WCQ)
# ---------------------------------------------------------------------------

def _scale_item_to_dict(row: ScaleItemResponse) -> dict:
    return {
        "id": str(row.id),
        "patient_id": row.user_id,
        "result_id": str(row.result_id),
        "scale_code": row.scale_code,
        "scale_version": row.scale_version,
        "question_id": row.question_id,
        "answer_value": row.answer_value,
        "measured_at": row.measured_at,
    }


async def get_scale_item_responses(
    session: AsyncSession,
    *,
    patient_id: Optional[int] = None,
    scale_code: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: Optional[int] = 500,
    offset: int = 0,
) -> list[dict]:
    dt_from, dt_to = _date_bounds(date_from, date_to)
    stmt = select(ScaleItemResponse)
    if patient_id is not None:
        stmt = stmt.where(ScaleItemResponse.user_id == patient_id)
    if scale_code is not None:
        stmt = stmt.where(ScaleItemResponse.scale_code == scale_code)
    if dt_from is not None:
        stmt = stmt.where(ScaleItemResponse.measured_at >= dt_from)
    if dt_to is not None:
        stmt = stmt.where(ScaleItemResponse.measured_at <= dt_to)
    stmt = stmt.order_by(ScaleItemResponse.measured_at.desc())
    if limit is not None:
        stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    return [_scale_item_to_dict(row) for row in result.scalars().all()]


# ---------------------------------------------------------------------------
# Медикаменты — adherence (простая метрика: приёмы/день vs frequency_times_per_day)
# ---------------------------------------------------------------------------

_MED_ADHERENCE_SQL = """
    WITH days AS (
        SELECT
            mp.patient_id,
            mp.id AS prescription_id,
            mp.frequency_times_per_day,
            gs::date AS day
        FROM medications.medication_prescriptions mp
        CROSS JOIN LATERAL generate_series(
            mp.start_date::timestamp,
            COALESCE(mp.end_date, CURRENT_DATE)::timestamp,
            interval '1 day'
        ) AS gs
        WHERE {rx_where}
    ),
    actual AS (
        SELECT
            mi.prescription_id,
            mi.intake_datetime::date AS day,
            COUNT(*) AS actual_count
        FROM medications.medication_intakes mi
        GROUP BY mi.prescription_id, mi.intake_datetime::date
    )
    SELECT
        d.patient_id                                AS patient_id,
        d.day                                        AS day,
        SUM(d.frequency_times_per_day)::int          AS expected_total,
        COALESCE(SUM(a.actual_count), 0)::int        AS actual_total
    FROM days d
    LEFT JOIN actual a
        ON a.prescription_id = d.prescription_id AND a.day = d.day
    WHERE {day_where}
    GROUP BY d.patient_id, d.day
    ORDER BY d.patient_id, d.day
"""


async def get_medication_adherence(
    session: AsyncSession,
    *,
    patient_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[dict]:
    rx_parts = ["1=1"]
    day_parts = ["1=1"]
    params: dict[str, Any] = {}

    if patient_id is not None:
        rx_parts.append("mp.patient_id = :patient_id")
        day_parts.append("d.patient_id = :patient_id")
        params["patient_id"] = patient_id
    if date_from is not None:
        day_parts.append("d.day >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        day_parts.append("d.day <= :date_to")
        params["date_to"] = date_to

    sql = _MED_ADHERENCE_SQL.format(
        rx_where=" AND ".join(rx_parts), day_where=" AND ".join(day_parts)
    )
    result = await session.execute(text(sql), params)

    out = []
    for row in result.mappings().all():
        expected = int(row["expected_total"] or 0)
        actual = int(row["actual_total"] or 0)
        pct = round(actual / expected * 100, 1) if expected > 0 else None
        day_val = row["day"]
        out.append(
            {
                "patient_id": row["patient_id"],
                "day": day_val.isoformat() if hasattr(day_val, "isoformat") else str(day_val),
                "expected_total": expected,
                "actual_total": actual,
                "adherence_pct": pct,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Практики — объединённая статистика (standalone + внутри уроков)
# ---------------------------------------------------------------------------

_PRACTICE_COMPLETIONS_SQL = """
    SELECT patient_id, source, practice_id, practice_title, completed_at,
           mood_after, success, effect_rating
    FROM (
        SELECT
            pc.patient_id               AS patient_id,
            'standalone'                AS source,
            pc.practice_id::text        AS practice_id,
            p.title                     AS practice_title,
            pc.completed_at::timestamp  AS completed_at,
            pc.mood_after               AS mood_after,
            NULL::boolean               AS success,
            NULL::integer               AS effect_rating
        FROM practices.practice_completions pc
        LEFT JOIN practices.practices p ON p.id = pc.practice_id
        WHERE {standalone_where}

        UNION ALL

        SELECT
            pl.user_id                  AS patient_id,
            'lesson'                    AS source,
            pl.practice_id::text        AS practice_id,
            ep.title                    AS practice_title,
            pl.performed_at::timestamp  AS completed_at,
            NULL::smallint              AS mood_after,
            pl.success                  AS success,
            pl.effect_rating            AS effect_rating
        FROM education.practice_logs pl
        LEFT JOIN education.practices ep ON ep.id = pl.practice_id
        WHERE {lesson_where}
    ) combined
    ORDER BY completed_at DESC
    {limit_clause}
"""


async def get_practice_completions(
    session: AsyncSession,
    *,
    patient_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: Optional[int] = 500,
    offset: int = 0,
) -> list[dict]:
    dt_from, dt_to = _date_bounds(date_from, date_to)
    standalone_parts = ["1=1"]
    lesson_parts = ["1=1"]
    params: dict[str, Any] = {}

    if patient_id is not None:
        standalone_parts.append("pc.patient_id = :patient_id")
        lesson_parts.append("pl.user_id = :patient_id")
        params["patient_id"] = patient_id
    if dt_from is not None:
        standalone_parts.append("pc.completed_at >= :date_from")
        lesson_parts.append("pl.performed_at >= :date_from")
        params["date_from"] = dt_from
    if dt_to is not None:
        standalone_parts.append("pc.completed_at <= :date_to")
        lesson_parts.append("pl.performed_at <= :date_to")
        params["date_to"] = dt_to

    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset

    sql = _PRACTICE_COMPLETIONS_SQL.format(
        standalone_where=" AND ".join(standalone_parts),
        lesson_where=" AND ".join(lesson_parts),
        limit_clause=limit_clause,
    )
    result = await session.execute(text(sql), params)
    return [dict(row) for row in result.mappings().all()]


# ---------------------------------------------------------------------------
# Уроки — тесты, по каждому вопросу (не только score)
# ---------------------------------------------------------------------------

async def get_education_test_results(
    session: AsyncSession,
    *,
    patient_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: Optional[int] = 500,
    offset: int = 0,
) -> list[dict]:
    dt_from, dt_to = _date_bounds(date_from, date_to)
    stmt = select(LessonTestResult, LessonTest.code, LessonTest.title).join(
        LessonTest, LessonTest.id == LessonTestResult.test_id
    )
    if patient_id is not None:
        stmt = stmt.where(LessonTestResult.user_id == patient_id)
    if dt_from is not None:
        stmt = stmt.where(LessonTestResult.created_at >= dt_from)
    if dt_to is not None:
        stmt = stmt.where(LessonTestResult.created_at <= dt_to)
    stmt = stmt.order_by(LessonTestResult.created_at.desc())
    if limit is not None:
        stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)

    out: list[dict] = []
    for test_result, test_code, test_title in result.all():
        base = {
            "patient_id": test_result.user_id,
            "test_code": test_code,
            "test_title": test_title,
            "created_at": test_result.created_at,
            "score": float(test_result.score),
            "max_score": float(test_result.max_score),
            "passed": test_result.passed,
        }
        answers = test_result.answers_json or []
        if not answers:
            out.append({**base, "question_id": None, "chosen_option": None, "is_correct": None})
            continue
        for ans in answers:
            out.append(
                {
                    **base,
                    "question_id": ans.get("question_id"),
                    "chosen_option": ans.get("chosen_option"),
                    "is_correct": ans.get("is_correct"),
                }
            )
    return out


# ---------------------------------------------------------------------------
# Сон
# ---------------------------------------------------------------------------

def _sleep_row_to_dict(row: SleepRecord) -> dict:
    return {
        "id": str(row.id),
        "patient_id": row.patient_id,
        "sleep_date": row.sleep_date,
        "sleep_onset": row.sleep_onset,
        "wake_time": row.wake_time,
        "tib_minutes": row.tib_minutes,
        "tst_minutes": row.tst_minutes,
        "sleep_efficiency_pct": row.sleep_efficiency_pct,
        "night_awakenings": row.night_awakenings,
        "sleep_latency": row.sleep_latency,
        "morning_wellbeing": row.morning_wellbeing,
        "daytime_nap": row.daytime_nap,
        "sleep_disturbances": list(row.sleep_disturbances) if row.sleep_disturbances else None,
        "late_entry": bool(row.late_entry),
        "retrospective_days": row.retrospective_days,
    }


async def get_sleep_records(
    session: AsyncSession,
    *,
    patient_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: Optional[int] = 500,
    offset: int = 0,
) -> list[dict]:
    stmt = select(SleepRecord)
    if patient_id is not None:
        stmt = stmt.where(SleepRecord.patient_id == patient_id)
    if date_from is not None:
        stmt = stmt.where(SleepRecord.sleep_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(SleepRecord.sleep_date <= date_to)
    stmt = stmt.order_by(SleepRecord.sleep_date.desc())
    if limit is not None:
        stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    return [_sleep_row_to_dict(row) for row in result.scalars().all()]


# ---------------------------------------------------------------------------
# Витальные показатели (АД, пульс, вес, вода)
# ---------------------------------------------------------------------------

_VITALS_MODELS = {
    "bp": BPMeasurement,
    "pulse": PulseMeasurement,
    "weight": WeightMeasurement,
    "water": WaterIntake,
}


def _vital_row_to_dict(vital_type: str, row) -> dict:
    base = {
        "id": str(row.id),
        "patient_id": row.user_id,
        "measured_at": row.measured_at,
        "context": row.context,
    }
    if vital_type == "bp":
        base.update({"systolic": row.systolic, "diastolic": row.diastolic, "pulse": row.pulse})
    elif vital_type == "pulse":
        base.update({"bpm": row.bpm})
    elif vital_type == "weight":
        base.update({"weight": float(row.weight) if row.weight is not None else None})
    elif vital_type == "water":
        base.update({"volume_ml": row.volume_ml, "liquid_type": row.liquid_type})
    return base


async def get_vitals_records(
    session: AsyncSession,
    *,
    vital_type: str,
    patient_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: Optional[int] = 500,
    offset: int = 0,
) -> list[dict]:
    model = _VITALS_MODELS.get(vital_type)
    if model is None:
        raise ValueError(f"Unknown vital_type: {vital_type!r}. Expected one of {sorted(_VITALS_MODELS)}")

    dt_from, dt_to = _date_bounds(date_from, date_to)
    stmt = select(model)
    if patient_id is not None:
        stmt = stmt.where(model.user_id == patient_id)
    if dt_from is not None:
        stmt = stmt.where(model.measured_at >= dt_from)
    if dt_to is not None:
        stmt = stmt.where(model.measured_at <= dt_to)
    stmt = stmt.order_by(model.measured_at.desc())
    if limit is not None:
        stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    return [_vital_row_to_dict(vital_type, row) for row in result.scalars().all()]


# ---------------------------------------------------------------------------
# Общий CSV/JSON экспорт (по образцу /chat-logs/export)
# ---------------------------------------------------------------------------

def build_export_response(
    rows: list[dict],
    columns: list[str],
    *,
    format: str,
    filename_prefix: str,
) -> StreamingResponse:
    """Стримит уже выбранные строки как CSV или JSON — общий хвост для всех
    export-эндпоинтов Track A (аналог существующего /chat-logs/export)."""

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    def _clean(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    if format == "json":
        data = [{c: _clean(row.get(c)) for c in columns} for row in rows]

        async def generate_json():
            yield json_module.dumps(data, ensure_ascii=False, indent=2, default=str)

        return StreamingResponse(
            generate_json(),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename_prefix}_{timestamp}.json"'
            },
        )

    async def generate_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        yield buf.getvalue()

        for row in rows:
            buf.seek(0)
            buf.truncate()
            values = [_clean(row.get(c)) for c in columns]
            writer.writerow(["" if v is None else v for v in values])
            yield buf.getvalue()

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_prefix}_{timestamp}.csv"'
        },
    )
