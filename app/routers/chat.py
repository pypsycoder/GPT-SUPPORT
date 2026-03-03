"""
Chat HTTP Router — эндпоинты для взаимодействия пациента с LLM-ассистентом.

POST /api/chat/message    — отправить сообщение, получить ответ
GET  /api/chat/history/{patient_id} — история сообщений
GET  /api/chat/pool/stats — статус пула аккаунтов (для диагностики)
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.llm.agent import generate_response
from app.llm.pool import pool
from app.llm.router import classify_request
from app.models.llm import ChatMessage
from app.users.models import User
from core.db.session import get_async_session

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


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
    pending_vitals: Optional[list] = None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    tokens_used: int
    model_used: Optional[str]
    domain: Optional[str]
    request_type: Optional[str]
    buttons_json: Optional[list] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# ---------------------------------------------------------------------------
# POST /message
# ---------------------------------------------------------------------------

@router.post("/message", response_model=MessageResponse)
async def send_message(
    body: MessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    """
    Принимает сообщение от пациента, возвращает ответ LLM-ассистента.
    Сохраняет оба сообщения (user + assistant) в chat_messages.
    """
    # Проверяем, что пациент запрашивает свой чат (или это admin)
    if current_user.id != body.patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к чату другого пациента",
        )

    wall_start = time.monotonic()

    # 1. Классифицируем запрос
    router_result = classify_request(body.message, body.source)

    # 2. Собираем дневной контекст для LLM (если есть — подставится в system prompt)
    from app.llm.morning_service import get_daily_context_for_llm
    daily_ctx = await get_daily_context_for_llm(body.patient_id, db)

    # 3. Генерируем ответ (с логированием в llm_request_logs)
    llm_result = await generate_response(
        patient_id=body.patient_id,
        user_input=body.message,
        router_result=router_result,
        context={"daily_context": daily_ctx},
        db=db,
    )

    elapsed_ms = int((time.monotonic() - wall_start) * 1000)
    tokens_total = llm_result["tokens_input"] + llm_result["tokens_output"]

    # 3. Сохраняем сообщение пользователя
    user_msg = ChatMessage(
        patient_id=body.patient_id,
        role="user",
        content=body.message,
        tokens_used=0,
        model_used=None,
        domain=llm_result["domain"],
        request_type=router_result.request_type.value,
    )
    db.add(user_msg)

    # 4. Сохраняем ответ ассистента (непрочитанным, пока пользователь не откроет чат)
    assistant_msg = ChatMessage(
        patient_id=body.patient_id,
        role="assistant",
        content=llm_result["response"],
        tokens_used=tokens_total,
        model_used=llm_result["model"],
        domain=llm_result["domain"],
        request_type=router_result.request_type.value,
        is_read=False,
    )
    db.add(assistant_msg)

    await db.commit()

    return MessageResponse(
        response=llm_result["response"],
        tokens_used=tokens_total,
        response_time_ms=elapsed_ms,
        domain=llm_result["domain"],
        model=llm_result["model"],
        pending_vitals=llm_result.get("pending_vitals"),
    )


# ---------------------------------------------------------------------------
# GET /history/{patient_id}
# ---------------------------------------------------------------------------

@router.get("/history/{patient_id}", response_model=list[ChatMessageOut])
async def get_history(
    patient_id: int,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[ChatMessageOut]:
    """
    Возвращает последние N сообщений чата пациента (user + assistant),
    отсортированных по created_at ASC.
    """
    if current_user.id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к истории другого пациента",
        )

    # Генерируем утреннее сообщение на лету, если cron ещё не отработал
    from app.llm.morning_service import ensure_morning_message
    await ensure_morning_message(patient_id, db)

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.patient_id == patient_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()

    # Разворачиваем в хронологический порядок
    messages = list(reversed(messages))

    return [
        ChatMessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            tokens_used=m.tokens_used,
            model_used=m.model_used,
            domain=m.domain,
            request_type=m.request_type,
            buttons_json=m.buttons_json,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


# ---------------------------------------------------------------------------
# POST /confirm-vitals
# ---------------------------------------------------------------------------


class ConfirmVitalsRequest(BaseModel):
    vitals: list[dict]
    confirmed: bool


@router.post("/confirm-vitals", status_code=200)
async def confirm_vitals(
    body: ConfirmVitalsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """
    Записывает витальные показатели в БД после подтверждения пациентом.
    Если confirmed=False — ничего не делает.
    """
    if not body.confirmed:
        return {"saved": 0}

    from app.vitals.models import BPMeasurement, PulseMeasurement, WeightMeasurement, WaterIntake
    from app.llm.parser import normalize_bp, normalize_pulse

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


# ---------------------------------------------------------------------------
# POST /mark-read  — пометить все непрочитанные сообщения ассистента прочитанными
# ---------------------------------------------------------------------------


from sqlalchemy import update as sa_update  # noqa: E402


@router.post("/mark-read", status_code=200)
async def mark_messages_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    """
    Помечает все непрочитанные сообщения ассистента пациента как прочитанные.
    Вызывается chat.js при открытии drawer.
    """
    await db.execute(
        sa_update(ChatMessage)
        .where(
            ChatMessage.patient_id == current_user.id,
            ChatMessage.role == "assistant",
            ChatMessage.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# GET /pool/stats (диагностика)
# ---------------------------------------------------------------------------

@router.get("/pool/stats")
async def get_pool_stats(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Возвращает статус пула аккаунтов GigaChat (для мониторинга)."""
    return pool.get_stats()
