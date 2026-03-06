# ============================================
# Researchers API: Панель исследователя
# ============================================
# Эндпоинты для создания пациентов, сброса PIN,
# просмотра списка пациентов и их данных.

"""API endpoints for researcher patient management."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, time as dt_time
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.session import get_async_session
from app.auth.dependencies import get_current_researcher
from app.researchers.models import Researcher
from app.researchers.schemas import (
    PatientCreateRequest,
    PatientCreateResponse,
    PatientListItem,
    PatientDetail,
    PatientCenterAssign,
    BulkPatientActionRequest,
    PinResetResponse,
    KdqolPointStatus,
    ChatLogItem,
    ChatLogsResponse,
    ChatStatsResponse,
    TokensByDate,
    CohortItem,
)
from app.researchers import crud

router = APIRouter(prefix="/researcher", tags=["researcher"])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/stats")
async def researcher_stats(
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Return basic patient statistics and usage stats for the researcher dashboard."""
    patient_stats = await crud.get_patients_stats(session)
    usage_stats = await crud.get_usage_stats(session)
    return {
        **patient_stats,
        "usage": usage_stats,
    }


# ---------------------------------------------------------------------------
# Patient list / create
# ---------------------------------------------------------------------------

def _patient_to_list_item(p, *, measurement_points=None, dialysis_schedules=None) -> PatientListItem:
    """Build PatientListItem with center, KDQOL points and active schedule."""
    mp_list = measurement_points if measurement_points is not None else getattr(p, 'measurement_points', []) or []
    sched_list = dialysis_schedules if dialysis_schedules is not None else getattr(p, 'dialysis_schedules', []) or []

    kdqol_points = [
        KdqolPointStatus(
            scale_code=mp.scale_code,
            point_type=mp.point_type,
            is_completed=mp.completed_at is not None,
            activated_at=mp.activated_at,
            completed_at=mp.completed_at,
        )
        for mp in mp_list
    ]

    active_schedule = next((s for s in sched_list if s.valid_to is None), None)

    return PatientListItem(
        id=p.id,
        patient_number=p.patient_number,
        full_name=p.full_name,
        age=p.age,
        gender=p.gender,
        is_locked=p.is_locked or False,
        consent_personal_data=p.consent_personal_data or False,
        consent_bot_use=p.consent_bot_use or False,
        center_id=str(p.center_id) if p.center_id else None,
        center_name=p.center.name if p.center else None,
        center_city=p.center.city if p.center else None,
        kdqol_points=kdqol_points,
        active_schedule_days=list(active_schedule.weekdays) if active_schedule else None,
        active_schedule_shift=str(active_schedule.shift) if active_schedule else None,
    )


@router.get("/patients", response_model=List[PatientListItem])
async def list_patients(
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Return all patients."""
    patients = await crud.list_patients(session)
    return [_patient_to_list_item(p) for p in patients]


@router.post("/patients", response_model=PatientCreateResponse, status_code=201)
async def create_patient(
    body: PatientCreateRequest,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new patient. Returns the generated PIN (shown only once)."""
    user, pin = await crud.create_patient(
        session,
        full_name=body.full_name,
        age=body.age,
        gender=body.gender,
    )
    return PatientCreateResponse(
        id=user.id,
        patient_number=user.patient_number,
        pin=pin,
        full_name=user.full_name,
    )


# ---------------------------------------------------------------------------
# Single patient
# ---------------------------------------------------------------------------

@router.get("/patients/{patient_id}", response_model=PatientDetail)
async def get_patient(
    patient_id: int,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Return details of a single patient."""
    user = await crud.get_patient_by_id(session, patient_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    return PatientDetail.model_validate(user)


@router.post("/patients/{patient_id}/reset-pin", response_model=PinResetResponse)
async def reset_pin(
    patient_id: int,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Reset the patient's PIN and unlock the account."""
    user = await crud.get_patient_by_id(session, patient_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    new_pin = await crud.reset_patient_pin(session, user)
    return PinResetResponse(patient_number=user.patient_number, new_pin=new_pin)


@router.post("/patients/{patient_id}/unlock")
async def unlock_patient(
    patient_id: int,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Unlock a locked patient account."""
    user = await crud.get_patient_by_id(session, patient_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    await crud.unlock_patient(session, user)
    return {"ok": True, "message": "Аккаунт разблокирован"}


@router.patch("/patients/{patient_id}/center")
async def assign_patient_center(
    patient_id: int,
    body: PatientCenterAssign,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Assign or clear dialysis center for a patient."""
    user = await crud.get_patient_by_id(session, patient_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пациент не найден")
    center_id: UUID | None = body.center_id
    if center_id is not None:
        from app.dialysis.crud import get_center_by_id
        center = await get_center_by_id(session, center_id)
        if center is None:
            raise HTTPException(status_code=400, detail="Центр диализа не найден")
    await crud.update_patient_center(session, user, center_id)
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.users.models import User
    result = await session.execute(
        select(User)
        .where(User.id == patient_id)
        .options(
            selectinload(User.center),
            selectinload(User.measurement_points),
            selectinload(User.dialysis_schedules),
        )
    )
    user = result.scalar_one()
    return _patient_to_list_item(user)


# ---------------------------------------------------------------------------
# Bulk patient actions
# ---------------------------------------------------------------------------

@router.post("/patients/bulk-delete")
async def bulk_delete_patients(
    body: BulkPatientActionRequest,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Hard-delete multiple patients by ID."""
    if not body.patient_ids:
        raise HTTPException(status_code=400, detail="Список пациентов пуст")
    deleted = await crud.bulk_delete_patients(session, body.patient_ids)
    return {"ok": True, "deleted": deleted}


@router.post("/patients/bulk-block")
async def bulk_block_patients(
    body: BulkPatientActionRequest,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Block (lock) multiple patients by ID."""
    if not body.patient_ids:
        raise HTTPException(status_code=400, detail="Список пациентов пуст")
    updated = await crud.bulk_block_patients(session, body.patient_ids)
    return {"ok": True, "blocked": updated}


# ---------------------------------------------------------------------------
# Chat log monitoring
# ---------------------------------------------------------------------------

_CHAT_LOG_SQL = """
    SELECT
        lrl.id                                      AS log_id,
        lrl.patient_id,
        lrl.created_at,
        lrl.request_type,
        lrl.model_tier,
        lrl.tokens_input,
        lrl.tokens_output,
        lrl.response_time_ms,
        lrl.success,
        lrl.error_message,
        cm_asst.domain                              AS domain,
        LEFT(cm_user.content, 300)                  AS user_content,
        LEFT(cm_asst.content, 300)                  AS assistant_content
    FROM llm.llm_request_logs lrl
    LEFT JOIN LATERAL (
        SELECT content
        FROM llm.chat_messages
        WHERE patient_id = lrl.patient_id
          AND role = 'user'
          AND created_at BETWEEN lrl.created_at - INTERVAL '120 seconds'
                             AND lrl.created_at + INTERVAL '120 seconds'
        ORDER BY ABS(EXTRACT(EPOCH FROM created_at - lrl.created_at))
        LIMIT 1
    ) cm_user ON true
    LEFT JOIN LATERAL (
        SELECT content, domain
        FROM llm.chat_messages
        WHERE patient_id = lrl.patient_id
          AND role = 'assistant'
          AND created_at BETWEEN lrl.created_at - INTERVAL '120 seconds'
                             AND lrl.created_at + INTERVAL '120 seconds'
        ORDER BY ABS(EXTRACT(EPOCH FROM created_at - lrl.created_at))
        LIMIT 1
    ) cm_asst ON true
    WHERE {where}
    ORDER BY lrl.created_at DESC
    LIMIT :limit OFFSET :offset
"""

_CHAT_LOG_COUNT_SQL = """
    SELECT
        COUNT(*)                                    AS total,
        COALESCE(AVG(lrl.response_time_ms), 0)      AS avg_ms
    FROM llm.llm_request_logs lrl
    LEFT JOIN LATERAL (
        SELECT content, domain
        FROM llm.chat_messages
        WHERE patient_id = lrl.patient_id
          AND role = 'assistant'
          AND created_at BETWEEN lrl.created_at - INTERVAL '120 seconds'
                             AND lrl.created_at + INTERVAL '120 seconds'
        ORDER BY ABS(EXTRACT(EPOCH FROM created_at - lrl.created_at))
        LIMIT 1
    ) cm_asst ON true
    WHERE {where}
"""

_SAFETY_TODAY_SQL = """
    SELECT COUNT(*) AS safety_today
    FROM llm.llm_request_logs
    WHERE request_type = 'safety'
      AND created_at >= CURRENT_DATE
      AND created_at < CURRENT_DATE + INTERVAL '1 day'
"""

_REQUEST_TYPES_TODAY_SQL = """
    SELECT request_type, COUNT(*) AS cnt
    FROM llm.llm_request_logs
    WHERE created_at >= CURRENT_DATE
      AND created_at < CURRENT_DATE + INTERVAL '1 day'
    GROUP BY request_type
"""


@router.get("/chat-logs", response_model=ChatLogsResponse)
async def get_chat_logs(
    patient_id: Optional[int] = None,
    domain: Optional[str] = None,
    request_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
) -> ChatLogsResponse:
    """Return paginated chat log entries for the researcher monitoring panel."""
    where_parts = ["1=1"]
    params: dict = {}

    if patient_id is not None:
        where_parts.append("lrl.patient_id = :patient_id")
        params["patient_id"] = patient_id

    if domain is not None:
        where_parts.append("cm_asst.domain = :domain")
        params["domain"] = domain

    if request_type is not None:
        where_parts.append("lrl.request_type = :request_type")
        params["request_type"] = request_type

    if date_from is not None:
        params["date_from"] = datetime.combine(date_from, dt_time.min)
        where_parts.append("lrl.created_at >= :date_from")

    if date_to is not None:
        params["date_to"] = datetime.combine(date_to, dt_time.max)
        where_parts.append("lrl.created_at <= :date_to")

    where_str = " AND ".join(where_parts)

    rows_result = await session.execute(
        text(_CHAT_LOG_SQL.format(where=where_str)),
        {**params, "limit": limit, "offset": offset},
    )
    rows = rows_result.mappings().all()

    stats_result = await session.execute(
        text(_CHAT_LOG_COUNT_SQL.format(where=where_str)),
        params,
    )
    stats_row = stats_result.mappings().one()

    safety_result = await session.execute(text(_SAFETY_TODAY_SQL))
    safety_row = safety_result.mappings().one()

    types_result = await session.execute(text(_REQUEST_TYPES_TODAY_SQL))
    request_types_today = {
        row["request_type"]: int(row["cnt"])
        for row in types_result.mappings().all()
        if row["request_type"]
    }

    items = [
        ChatLogItem(
            log_id=row["log_id"],
            patient_id=row["patient_id"],
            created_at=row["created_at"],
            domain=row["domain"],
            request_type=row["request_type"],
            model_tier=row["model_tier"],
            user_content=row["user_content"],
            assistant_content=row["assistant_content"],
            tokens_input=row["tokens_input"] or 0,
            tokens_output=row["tokens_output"] or 0,
            response_time_ms=row["response_time_ms"] or 0,
            success=bool(row["success"]),
            error_message=row["error_message"],
        )
        for row in rows
    ]

    return ChatLogsResponse(
        total=int(stats_row["total"]),
        safety_today=int(safety_row["safety_today"]),
        avg_response_ms=round(float(stats_row["avg_ms"]), 1),
        request_types_today=request_types_today,
        items=items,
    )


# ---------------------------------------------------------------------------
# Cohorts
# ---------------------------------------------------------------------------

_COHORTS_SQL = """
    SELECT
        u.center_id::text                           AS center_id,
        c.name                                      AS center_name,
        ds.shift::text                              AS shift,
        ds.weekdays,
        COUNT(DISTINCT ds.patient_id)               AS patient_count
    FROM public.dialysis_schedules ds
    JOIN users.users u ON u.id = ds.patient_id
    JOIN public.centers c ON c.id = u.center_id
    WHERE ds.valid_to IS NULL
      {center_filter}
    GROUP BY u.center_id, c.name, ds.shift, ds.weekdays
    ORDER BY c.name, ds.shift
"""

_WEEKDAY_NAMES = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
_SHIFT_LABELS  = {"morning": "Утро", "afternoon": "День", "evening": "Вечер"}


def _make_cohort_id(center_uuid_str: str, shift: str, weekdays: list[int]) -> str:
    prefix = center_uuid_str.replace("-", "")[:8]
    wd_str = "".join(str(d) for d in sorted(weekdays))
    return f"{prefix}_{shift}_{wd_str}"


def _make_cohort_label(center_name: str, shift: str, weekdays: list[int]) -> str:
    city = center_name.split()[-1] if center_name else center_name
    shift_label = _SHIFT_LABELS.get(shift, shift)
    wd_labels = "-".join(_WEEKDAY_NAMES.get(d, str(d)) for d in sorted(weekdays))
    return f"{city} / {shift_label} / {wd_labels}"


@router.get("/cohorts", response_model=list[CohortItem])
async def get_cohorts(
    center_id: Optional[UUID] = None,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
) -> list[CohortItem]:
    """Return distinct dialysis cohorts (center × shift × weekdays) with patient counts."""
    center_filter = "AND u.center_id = :center_id::uuid" if center_id is not None else ""
    params: dict = {}
    if center_id is not None:
        params["center_id"] = str(center_id)

    result = await session.execute(
        text(_COHORTS_SQL.format(center_filter=center_filter)), params
    )
    rows = result.mappings().all()

    cohorts = []
    for row in rows:
        cid_str = row["center_id"] or ""
        shift = row["shift"] or ""
        weekdays = sorted(list(row["weekdays"] or []))
        cohorts.append(CohortItem(
            cohort_id=_make_cohort_id(cid_str, shift, weekdays),
            center_id=cid_str,
            center_name=row["center_name"] or "",
            shift=shift,
            weekdays=weekdays,
            patient_count=int(row["patient_count"]),
            label=_make_cohort_label(row["center_name"] or "", shift, weekdays),
        ))
    return cohorts


# ---------------------------------------------------------------------------
# Chat analytics (charts)
# ---------------------------------------------------------------------------

_STATS_TOKENS_SQL = """
    SELECT
        DATE(lrl.created_at)   AS day,
        SUM(lrl.tokens_input)  AS input,
        SUM(lrl.tokens_output) AS output
    FROM llm.llm_request_logs lrl
    WHERE {where}
    GROUP BY DATE(lrl.created_at)
    ORDER BY DATE(lrl.created_at)
"""

_STATS_MODELS_SQL = """
    SELECT lrl.model_tier, COUNT(*) AS cnt
    FROM llm.llm_request_logs lrl
    WHERE {where}
    GROUP BY lrl.model_tier
"""

_STATS_DOMAINS_SQL = """
    SELECT cm.domain, COUNT(*) AS cnt
    FROM llm.chat_messages cm
    WHERE cm.role = 'assistant'
      AND cm.domain IS NOT NULL
      AND {where}
    GROUP BY cm.domain
"""

_STATS_HOURS_SQL = """
    SELECT EXTRACT(HOUR FROM lrl.created_at)::int AS hour, COUNT(*) AS cnt
    FROM llm.llm_request_logs lrl
    WHERE {where}
    GROUP BY EXTRACT(HOUR FROM lrl.created_at)
    ORDER BY hour
"""

_STATS_WEEKDAY_SQL = """
    SELECT EXTRACT(ISODOW FROM lrl.created_at)::int AS dow, COUNT(*) AS cnt
    FROM llm.llm_request_logs lrl
    WHERE {where}
    GROUP BY EXTRACT(ISODOW FROM lrl.created_at)
    ORDER BY dow
"""

_STATS_DIALYSIS_SQL = """
    SELECT
        SUM(CASE WHEN is_dialysis THEN 1 ELSE 0 END)     AS dialysis_day,
        SUM(CASE WHEN NOT is_dialysis THEN 1 ELSE 0 END)  AS non_dialysis_day
    FROM (
        SELECT
            EXISTS (
                SELECT 1
                FROM public.dialysis_schedules ds
                WHERE ds.patient_id = lrl.patient_id
                  AND EXTRACT(ISODOW FROM lrl.created_at) = ANY(ds.weekdays)
                  AND ds.valid_from <= lrl.created_at::date
                  AND (ds.valid_to IS NULL OR ds.valid_to >= lrl.created_at::date)
            ) AS is_dialysis
        FROM llm.llm_request_logs lrl
        WHERE {where}
    ) sub
"""


def _parse_cohort_id(cohort_id: str) -> tuple[str, str, list[int]]:
    """Parse '319e0b8d_morning_135' → (prefix, shift, [1,3,5])."""
    parts = cohort_id.split("_", 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid cohort_id: {cohort_id!r}")
    prefix, shift, wd_str = parts
    weekdays = sorted(int(c) for c in wd_str if c.isdigit())
    return prefix, shift, weekdays


@router.get("/chat-stats", response_model=ChatStatsResponse)
async def get_chat_stats(
    patient_id: Optional[int] = None,
    center_id: Optional[UUID] = None,
    cohort_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
) -> ChatStatsResponse:
    """Return aggregated analytics for the researcher chart panel."""
    lrl_parts = ["1=1"]
    cm_parts  = ["1=1"]
    params: dict = {}

    if patient_id is not None:
        lrl_parts.append("lrl.patient_id = :patient_id")
        cm_parts.append("cm.patient_id = :patient_id")
        params["patient_id"] = patient_id

    elif cohort_id is not None:
        # Parse cohort → filter by center prefix + schedule shift+weekdays
        try:
            c_prefix, c_shift, c_weekdays = _parse_cohort_id(cohort_id)
        except ValueError:
            pass
        else:
            cohort_subq = (
                "SELECT ds.patient_id"
                " FROM public.dialysis_schedules ds"
                " JOIN users.users u ON u.id = ds.patient_id"
                " WHERE ds.valid_to IS NULL"
                "   AND LEFT(u.center_id::text, 8) = :cohort_prefix"
                "   AND ds.shift::text = :cohort_shift"
                "   AND ds.weekdays = :cohort_weekdays"
            )
            lrl_parts.append(f"lrl.patient_id IN ({cohort_subq})")
            cm_parts.append(f"cm.patient_id IN ({cohort_subq})")
            params["cohort_prefix"] = c_prefix
            params["cohort_shift"]  = c_shift
            params["cohort_weekdays"] = c_weekdays

    elif center_id is not None:
        subq = "(SELECT id FROM users.users WHERE center_id = :center_id::uuid)"
        lrl_parts.append(f"lrl.patient_id IN {subq}")
        cm_parts.append(f"cm.patient_id IN {subq}")
        params["center_id"] = str(center_id)

    if date_from is not None:
        params["date_from"] = datetime.combine(date_from, dt_time.min)
        lrl_parts.append("lrl.created_at >= :date_from")
        cm_parts.append("cm.created_at >= :date_from")

    if date_to is not None:
        params["date_to"] = datetime.combine(date_to, dt_time.max)
        lrl_parts.append("lrl.created_at <= :date_to")
        cm_parts.append("cm.created_at <= :date_to")

    lrl_where = " AND ".join(lrl_parts)
    cm_where  = " AND ".join(cm_parts)

    tokens_res, models_res, domains_res, hours_res, weekday_res, dialysis_res = (
        await session.execute(text(_STATS_TOKENS_SQL.format(where=lrl_where)),  params),
        await session.execute(text(_STATS_MODELS_SQL.format(where=lrl_where)),  params),
        await session.execute(text(_STATS_DOMAINS_SQL.format(where=cm_where)),  params),
        await session.execute(text(_STATS_HOURS_SQL.format(where=lrl_where)),   params),
        await session.execute(text(_STATS_WEEKDAY_SQL.format(where=lrl_where)), params),
        await session.execute(text(_STATS_DIALYSIS_SQL.format(where=lrl_where)), params),
    )

    tokens_by_date = [
        TokensByDate(
            date=str(row["day"]),
            input=int(row["input"] or 0),
            output=int(row["output"] or 0),
        )
        for row in tokens_res.mappings().all()
    ]
    models_distribution = {
        row["model_tier"]: int(row["cnt"])
        for row in models_res.mappings().all()
        if row["model_tier"]
    }
    domains_distribution = {
        row["domain"]: int(row["cnt"])
        for row in domains_res.mappings().all()
        if row["domain"]
    }
    activity_by_hour = {
        str(row["hour"]): int(row["cnt"])
        for row in hours_res.mappings().all()
    }
    activity_by_weekday = {
        str(row["dow"]): int(row["cnt"])
        for row in weekday_res.mappings().all()
    }

    dialysis_row = dialysis_res.mappings().one_or_none()
    dialysis_vs_nondialysis: Optional[dict] = None
    if dialysis_row is not None:
        d_day = int(dialysis_row["dialysis_day"] or 0)
        n_day = int(dialysis_row["non_dialysis_day"] or 0)
        if d_day + n_day > 0:
            dialysis_vs_nondialysis = {
                "dialysis_day": d_day,
                "non_dialysis_day": n_day,
            }

    return ChatStatsResponse(
        tokens_by_date=tokens_by_date,
        models_distribution=models_distribution,
        domains_distribution=domains_distribution,
        activity_by_hour=activity_by_hour,
        activity_by_weekday=activity_by_weekday,
        dialysis_vs_nondialysis=dialysis_vs_nondialysis,
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

_EXPORT_SQL = """
    SELECT
        lrl.id,
        lrl.patient_id,
        u.center_id::text                           AS center_id,
        lrl.created_at,
        cm_asst.domain                              AS domain,
        lrl.request_type,
        lrl.model_tier,
        lrl.tokens_input,
        lrl.tokens_output,
        lrl.response_time_ms,
        lrl.success,
        LEFT(cm_user.content, 200)                  AS question_preview,
        LEFT(cm_asst.content, 200)                  AS answer_preview
    FROM llm.llm_request_logs lrl
    LEFT JOIN users.users u ON u.id = lrl.patient_id
    LEFT JOIN LATERAL (
        SELECT content
        FROM llm.chat_messages
        WHERE patient_id = lrl.patient_id
          AND role = 'user'
          AND created_at BETWEEN lrl.created_at - INTERVAL '120 seconds'
                             AND lrl.created_at + INTERVAL '120 seconds'
        ORDER BY ABS(EXTRACT(EPOCH FROM created_at - lrl.created_at))
        LIMIT 1
    ) cm_user ON true
    LEFT JOIN LATERAL (
        SELECT content, domain
        FROM llm.chat_messages
        WHERE patient_id = lrl.patient_id
          AND role = 'assistant'
          AND created_at BETWEEN lrl.created_at - INTERVAL '120 seconds'
                             AND lrl.created_at + INTERVAL '120 seconds'
        ORDER BY ABS(EXTRACT(EPOCH FROM created_at - lrl.created_at))
        LIMIT 1
    ) cm_asst ON true
    WHERE {where}
    ORDER BY lrl.created_at DESC
"""

_EXPORT_CSV_COLUMNS = [
    "id", "patient_id", "center_id", "created_at",
    "domain", "request_type", "model_tier",
    "tokens_input", "tokens_output", "response_time_ms", "success",
    "question_preview", "answer_preview",
]

_EXPORT_CSV_COLUMNS_META = [
    "id", "patient_id", "center_id", "created_at",
    "domain", "request_type", "model_tier",
    "tokens_input", "tokens_output", "response_time_ms", "success",
]


@router.get("/chat-logs/export")
async def export_chat_logs(
    patient_id: Optional[int] = None,
    center_id: Optional[UUID] = None,
    domain: Optional[str] = None,
    request_type: Optional[str] = None,
    model_tier: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    format: str = "csv",
    include_content: bool = True,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Export chat logs as CSV or JSON. Applies the same filters as /chat-logs."""
    where_parts = ["1=1"]
    params: dict = {}

    if patient_id is not None:
        where_parts.append("lrl.patient_id = :patient_id")
        params["patient_id"] = patient_id

    if center_id is not None:
        where_parts.append("u.center_id = :center_id::uuid")
        params["center_id"] = str(center_id)

    if domain is not None:
        where_parts.append("cm_asst.domain = :domain")
        params["domain"] = domain

    if request_type is not None:
        where_parts.append("lrl.request_type = :request_type")
        params["request_type"] = request_type

    if model_tier is not None:
        where_parts.append("lrl.model_tier = :model_tier")
        params["model_tier"] = model_tier

    if date_from is not None:
        params["date_from"] = datetime.combine(date_from, dt_time.min)
        where_parts.append("lrl.created_at >= :date_from")

    if date_to is not None:
        params["date_to"] = datetime.combine(date_to, dt_time.max)
        where_parts.append("lrl.created_at <= :date_to")

    where_str = " AND ".join(where_parts)

    result = await session.execute(
        text(_EXPORT_SQL.format(where=where_str)), params
    )
    rows = result.mappings().all()

    columns = _EXPORT_CSV_COLUMNS if include_content else _EXPORT_CSV_COLUMNS_META
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if format == "json":
        def _serialize(row: dict) -> dict:
            out = {c: row[c] for c in columns if c in row}
            if "created_at" in out and out["created_at"] is not None:
                out["created_at"] = out["created_at"].isoformat()
            out["success"] = bool(out.get("success"))
            return out

        data = [_serialize(dict(r)) for r in rows]

        async def generate_json():
            yield json.dumps(data, ensure_ascii=False, indent=2)

        return StreamingResponse(
            generate_json(),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="chat_logs_{timestamp}.json"'
            },
        )

    # CSV streaming
    async def generate_csv():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        yield buf.getvalue()

        for row in rows:
            buf.seek(0)
            buf.truncate()
            writer.writerow([
                row.get(c, "") if row.get(c) is not None else ""
                for c in columns
            ])
            yield buf.getvalue()

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f'attachment; filename="chat_logs_{timestamp}.csv"'
        },
    )
