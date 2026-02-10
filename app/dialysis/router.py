# ============================================
# Dialysis API: Центры и расписания диализа
# ============================================
# Все эндпоинты только для роли researcher.

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.session import get_async_session
from app.auth.dependencies import get_current_researcher
from app.researchers.models import Researcher
from app.researchers import crud as researcher_crud
from app.dialysis import crud, csv_import
from app.dialysis.models import DialysisSchedule
from app.dialysis.schemas import (
    CenterCreate,
    CenterRead,
    DialysisScheduleCreate,
    DialysisScheduleRead,
    ImportConfirmRequest,
    ImportConfirmResponse,
    ScheduleCloseAndReplaceResponse,
)

router = APIRouter(tags=["dialysis"])

# In-memory store for import previews. TTL 10 minutes.
# TODO: Replace with Redis when scaling.
IMPORT_PREVIEWS: dict[str, dict] = {}  # token -> { "data": preview, "expires_at": datetime }
IMPORT_PREVIEW_TTL_MINUTES = 10


# ---------------------------------------------------------------------------
# Centers
# ---------------------------------------------------------------------------

@router.get("/centers", response_model=list[CenterRead])
async def list_centers(
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    centers = await crud.list_centers(session)
    return [CenterRead.model_validate(c) for c in centers]


@router.post("/centers", response_model=CenterRead, status_code=status.HTTP_201_CREATED)
async def create_center(
    body: CenterCreate,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    if not (body.name or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Название центра обязательно")
    center = await crud.create_center(
        session,
        name=body.name.strip(),
        city=body.city.strip() if body.city else None,
        timezone=body.timezone or "Europe/Moscow",
    )
    return CenterRead.model_validate(center)


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------

def _schedule_to_read(s: DialysisSchedule) -> DialysisScheduleRead:
    return DialysisScheduleRead(
        id=s.id,
        patient_id=s.patient_id,
        weekdays=list(s.weekdays) if s.weekdays else [],
        shift=s.shift,
        valid_from=s.valid_from,
        valid_to=s.valid_to,
        created_at=s.created_at,
        created_by=s.created_by,
        closed_at=s.closed_at,
        closed_by=s.closed_by,
        change_reason=s.change_reason,
    )


@router.get("/patients/{patient_id}/schedules", response_model=list[DialysisScheduleRead])
async def list_patient_schedules(
    patient_id: int,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    user = await researcher_crud.get_patient_by_id(session, patient_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пациент не найден")
    schedules = await crud.list_schedules_for_patient(session, patient_id)
    return [_schedule_to_read(s) for s in schedules]


@router.post(
    "/patients/{patient_id}/schedules",
    response_model=DialysisScheduleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_patient_schedule(
    patient_id: int,
    body: DialysisScheduleCreate,
    researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    user = await researcher_crud.get_patient_by_id(session, patient_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пациент не найден")
    active = await crud.get_active_schedule(session, patient_id)
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "У пациента уже есть активное расписание",
                "existing_schedule": _schedule_to_read(active),
            },
        )
    schedule = await crud.create_schedule(
        session,
        patient_id=patient_id,
        weekdays=body.weekdays,
        shift=body.shift,
        valid_from=body.valid_from,
        created_by=researcher.id,
        change_reason=body.change_reason,
    )
    await session.commit()
    return _schedule_to_read(schedule)


@router.put(
    "/schedules/{schedule_id}/close-and-replace",
    response_model=ScheduleCloseAndReplaceResponse,
)
async def close_and_replace_schedule(
    schedule_id: UUID,
    body: DialysisScheduleCreate,
    researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    existing = await crud.get_schedule_by_id(session, schedule_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Расписание не найдено")
    old_valid_to = body.valid_from - timedelta(days=1)
    await crud.close_schedule(
        session,
        existing,
        valid_to=old_valid_to,
        closed_by=researcher.id,
        change_reason=body.change_reason,
    )
    await session.refresh(existing)
    new_schedule = await crud.create_schedule(
        session,
        patient_id=existing.patient_id,
        weekdays=body.weekdays,
        shift=body.shift,
        valid_from=body.valid_from,
        created_by=researcher.id,
        change_reason=body.change_reason,
    )
    await session.commit()
    return ScheduleCloseAndReplaceResponse(
        closed=_schedule_to_read(existing),
        created=_schedule_to_read(new_schedule),
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@router.post("/import/schedules")
async def import_schedules_preview(
    file: UploadFile = File(...),
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    content = await file.read()
    preview = await csv_import.parse_and_preview(session, content)
    token = uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=IMPORT_PREVIEW_TTL_MINUTES)
    IMPORT_PREVIEWS[token] = {"data": preview, "expires_at": expires_at}
    return {"preview_token": token, **preview}


@router.post("/import/schedules/confirm", response_model=ImportConfirmResponse)
async def import_schedules_confirm(
    body: ImportConfirmRequest,
    researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    now = datetime.now(timezone.utc)
    entry = IMPORT_PREVIEWS.get(body.preview_token)
    if entry is None or entry["expires_at"] <= now:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Токен превью истёк или не найден. Загрузите файл заново.",
        )
    preview = entry["data"]
    conflict_actions = {r.patient_id: r.action for r in body.resolve_conflicts}
    applied = 0
    skipped = 0
    errors: list[dict] = []
    try:
        if body.apply_ready:
            for item in preview["ready"]:
                p = item["parsed_schedule"]
                pid = p["patient_id"]
                active = await crud.get_active_schedule(session, pid)
                if active is not None:
                    errors.append({"patient_id": pid, "message": "Появилось активное расписание"})
                    continue
                try:
                    await crud.create_schedule(
                        session,
                        patient_id=pid,
                        weekdays=p["weekdays"],
                        shift=p["shift"],
                        valid_from=datetime.fromisoformat(p["valid_from"]).date(),
                        created_by=researcher.id,
                        change_reason=p.get("change_reason"),
                    )
                    applied += 1
                except Exception as e:
                    errors.append({"patient_id": pid, "message": str(e)})
        for item in preview["conflicts"]:
            pid = item["existing_schedule"]["patient_id"]
            action = conflict_actions.get(pid, "skip")
            if action == "skip":
                skipped += 1
                continue
            existing = await crud.get_schedule_by_id(session, UUID(item["existing_schedule"]["id"]))
            if existing is None:
                errors.append({"patient_id": pid, "message": "Расписание не найдено"})
                skipped += 1
                continue
            new_p = item["new_schedule"]
            valid_from = datetime.fromisoformat(new_p["valid_from"]).date()
            old_valid_to = valid_from - timedelta(days=1)
            await crud.close_schedule(
                session,
                existing,
                valid_to=old_valid_to,
                closed_by=researcher.id,
                change_reason=new_p.get("change_reason"),
            )
            await session.refresh(existing)
            await crud.create_schedule(
                session,
                patient_id=pid,
                weekdays=new_p["weekdays"],
                shift=new_p["shift"],
                valid_from=valid_from,
                created_by=researcher.id,
                change_reason=new_p.get("change_reason"),
            )
            applied += 1
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        IMPORT_PREVIEWS.pop(body.preview_token, None)
    return ImportConfirmResponse(applied=applied, skipped=skipped, errors=errors)
