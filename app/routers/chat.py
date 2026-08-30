"""
Chat HTTP router for patient <-> LLM interaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.llm.pipeline import LLMPipeline, LLMRequest
from app.llm.pool import pool
from app.llm import memory_store, rate_limit, vitals_writer
from app.llm.on_login import run_login_proactive
from app.llm.router_cascade import classify_request_async
from app.models.llm import ChatMessage, ChatSupervisorState
from app.users.models import User
from core.db.session import get_async_session

router = APIRouter()
_llm_pipeline = LLMPipeline()
_DEFAULT_THREAD_ID = "default"
_SESSION_TIMEOUT_HOURS = 8

# Fields that belong to the current expert session — cleared on reset.
# Accumulated patient context (facts, signals, risk_flags, domain) is kept.
_SESSION_RESET_FIELDS: dict = {
    "goal": None,
    "slots": {},
    "pending_question": None,
    "last_selected_agents": [],
    "needs_clarification": False,
    "clarification_streak": 0,
    "last_clarification_reason": None,
    "last_goal_status": None,
    "last_bot_reply": None,
    "current_technique_id": None,
    "current_technique_turns": 0,
    "current_step_index": 0,
    "recent_technique_ids": [],
    "anchor_goal": None,
}


def _reset_session_state(state: dict | None) -> dict:
    result = dict(state or {})
    result.update(_SESSION_RESET_FIELDS)
    return result


class MessageRequest(BaseModel):
    patient_id: int
    message: str = Field(..., min_length=1, max_length=4000)
    source: str = Field(default="text", description="text | button | system")


class MessageResponse(BaseModel):
    response: str
    tokens_used: int
    response_time_ms: int
    domain: Optional[str]
    model: str
    # pending_vitals остаётся для старого потока подтверждения (confirm-vitals).
    # Запись показателей через L0 его не использует: она уже записала и отдаёт
    # кнопку отмены.
    pending_vitals: Optional[list] = None
    buttons: Optional[list] = None
    education_cta: Optional[dict] = None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    tokens_used: int
    model_used: Optional[str]
    domain: Optional[str]
    request_type: Optional[str]
    created_at: str

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


async def _read_supervisor_state(db: AsyncSession, patient_id: int) -> dict | None:
    result = await db.execute(
        select(ChatSupervisorState.state_json, ChatSupervisorState.updated_at).where(
            ChatSupervisorState.patient_id == patient_id,
            ChatSupervisorState.thread_id == _DEFAULT_THREAD_ID,
        )
    )
    row = result.first()
    if row is None:
        return None
    state_json, updated_at = row
    state = dict(state_json) if isinstance(state_json, dict) else None
    if state is not None and updated_at is not None:
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        elapsed_hours = (datetime.now(tz=timezone.utc) - updated_at).total_seconds() / 3600
        if elapsed_hours >= _SESSION_TIMEOUT_HOURS:
            return _reset_session_state(state)
    return state


async def _write_supervisor_state(
    db: AsyncSession,
    *,
    patient_id: int,
    supervisor_state: dict | None,
) -> None:
    if not supervisor_state:
        return

    result = await db.execute(
        select(ChatSupervisorState).where(
            ChatSupervisorState.patient_id == patient_id,
            ChatSupervisorState.thread_id == _DEFAULT_THREAD_ID,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(
            ChatSupervisorState(
                patient_id=patient_id,
                thread_id=_DEFAULT_THREAD_ID,
                state_json=dict(supervisor_state),
            )
        )
    else:
        row.state_json = dict(supervisor_state)


class UndoVitalsRequest(BaseModel):
    patient_id: int
    entries: list[dict]


class UndoVitalsResponse(BaseModel):
    removed: int


@router.post("/undo-vitals", response_model=UndoVitalsResponse)
async def undo_vitals(
    body: UndoVitalsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> UndoVitalsResponse:
    """Убрать показатели, записанные последним ходом чата.

    Идентификаторы приходят из кнопки, но доверять им нельзя: удаляем только
    строки этого пациента, проверка внутри vitals_writer.undo().
    """
    if current_user.id != body.patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к данным другого пациента",
        )

    removed = await vitals_writer.undo(db, body.patient_id, body.entries)
    await db.commit()
    return UndoVitalsResponse(removed=removed)


@router.post("/message", response_model=MessageResponse)
async def send_message(
    body: MessageRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    if current_user.id != body.patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к чату другого пациента",
        )

    rate_limit.check(current_user.id)

    router_result = await classify_request_async(body.message, body.source)
    supervisor_state = await _read_supervisor_state(db, body.patient_id)
    llm_response = await _llm_pipeline.process(
        LLMRequest(
            patient_id=body.patient_id,
            user_input=body.message,
            source=body.source,
            supervisor_state=supervisor_state,
            router_result=router_result,
            db=db,
            thread_id=_DEFAULT_THREAD_ID,
        )
    )
    tokens_total = llm_response.tokens_input + llm_response.tokens_output

    db.add(
        ChatMessage(
            patient_id=body.patient_id,
            thread_id=_DEFAULT_THREAD_ID,
            role="user",
            content=body.message,
            tokens_used=0,
            model_used=None,
            domain=llm_response.domain,
            request_type=router_result.request_type.value,
        )
    )
    # Показатели распознал pipeline, но записывает их роутер: commit по правилам
    # проекта живёт только здесь. Кнопка отмены несёт идентификаторы созданных
    # строк, чтобы убрать ровно их, а не последнюю запись пациента.
    undo_buttons = None
    if llm_response.pending_vitals:
        created = await vitals_writer.write(db, body.patient_id, llm_response.pending_vitals)
        if created:
            undo_buttons = [
                {"label": "Отменить", "action": "undo_vitals", "payload": {"entries": created}}
            ]

    db.add(
        ChatMessage(
            patient_id=body.patient_id,
            thread_id=_DEFAULT_THREAD_ID,
            role="assistant",
            content=llm_response.response,
            tokens_used=tokens_total,
            model_used=llm_response.model,
            domain=llm_response.domain,
            request_type=router_result.request_type.value,
            buttons_json=undo_buttons,
        )
    )
    await _write_supervisor_state(
        db,
        patient_id=body.patient_id,
        supervisor_state=llm_response.supervisor_state,
    )
    await db.commit()

    # Свёртка вытесненных из окна ходов — вне критического пути ответа.
    # Своя сессия внутри: request-сессия уже закрывается к моменту запуска.
    background_tasks.add_task(memory_store.maybe_compact, body.patient_id, _DEFAULT_THREAD_ID)

    return MessageResponse(
        response=llm_response.response,
        tokens_used=tokens_total,
        response_time_ms=llm_response.response_time_ms,
        domain=llm_response.domain,
        model=llm_response.model,
        buttons=undo_buttons,
        education_cta=llm_response.education_cta,
    )


@router.get("/history/{patient_id}", response_model=list[ChatMessageOut])
async def get_history(
    patient_id: int,
    background_tasks: BackgroundTasks,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[ChatMessageOut]:
    if current_user.id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к истории другого пациента",
        )

    # Ленивый триггер проактива при входе — страховка на случай, если фоновый
    # вызов после логина не отработал (рестарт, вход вчера с живой сессией).
    # Идемпотентно: каждая доставка отсекает повтор за день.
    if current_user.is_onboarded and current_user.consent_personal_data:
        background_tasks.add_task(run_login_proactive, patient_id)

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.patient_id == patient_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))

    return [
        ChatMessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            tokens_used=m.tokens_used,
            model_used=m.model_used,
            domain=m.domain,
            request_type=m.request_type,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


class MarkReadResponse(BaseModel):
    updated: int


@router.post("/mark-read", response_model=MarkReadResponse)
async def mark_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> MarkReadResponse:
    """Отметить все сообщения ассистента прочитанными.

    Фронт зовёт при открытии чата — гасит бейдж `assistant` в сайдбаре.
    Проактив (`morning` / `motivator` / `proactive`) кладёт свои сообщения с
    `is_read=False`, здесь они и закрываются.
    """
    result = await db.execute(
        update(ChatMessage)
        .where(
            ChatMessage.patient_id == current_user.id,
            ChatMessage.role == "assistant",
            ChatMessage.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.commit()
    return MarkReadResponse(updated=result.rowcount or 0)


class ConfirmVitalsRequest(BaseModel):
    vitals: list[dict]
    confirmed: bool


@router.post("/confirm-vitals", status_code=200)
async def confirm_vitals(
    body: ConfirmVitalsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    if not body.confirmed:
        return {"saved": 0}

    from app.llm.parser import normalize_bp, normalize_pulse
    from app.vitals.models import BPMeasurement, PulseMeasurement, WaterIntake, WeightMeasurement

    saved = 0
    for v in body.vitals:
        vtype = str(v.get("type", "")).upper()
        value = v.get("value", "")
        try:
            if vtype == "BP":
                bp = normalize_bp(value)
                if bp is not None:
                    db.add(BPMeasurement(user_id=current_user.id, systolic=bp[0], diastolic=bp[1]))
                    saved += 1
            elif vtype == "PULSE":
                bpm = normalize_pulse(value)
                if bpm is not None:
                    db.add(PulseMeasurement(user_id=current_user.id, bpm=bpm))
                    saved += 1
            elif vtype == "WEIGHT":
                db.add(WeightMeasurement(user_id=current_user.id, weight=float(str(value).strip())))
                saved += 1
            elif vtype == "WATER":
                db.add(WaterIntake(user_id=current_user.id, volume_ml=int(float(str(value).strip()))))
                saved += 1
        except (ValueError, AttributeError):
            pass

    await db.commit()
    return {"saved": saved}


@router.post("/reset-session", status_code=200)
async def reset_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    result = await db.execute(
        select(ChatSupervisorState).where(
            ChatSupervisorState.patient_id == current_user.id,
            ChatSupervisorState.thread_id == _DEFAULT_THREAD_ID,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        row.state_json = _reset_session_state(dict(row.state_json))
    await db.commit()
    return {"ok": True}


@router.get("/pool/stats")
async def get_pool_stats(current_user: User = Depends(get_current_user)) -> dict:
    return pool.get_stats()
