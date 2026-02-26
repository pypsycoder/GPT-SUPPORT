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

    # 2. Генерируем ответ (с логированием в llm_request_logs)
    llm_result = await generate_response(
        patient_id=body.patient_id,
        user_input=body.message,
        router_result=router_result,
        context={},
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

    # 4. Сохраняем ответ ассистента
    assistant_msg = ChatMessage(
        patient_id=body.patient_id,
        role="assistant",
        content=llm_result["response"],
        tokens_used=tokens_total,
        model_used=llm_result["model"],
        domain=llm_result["domain"],
        request_type=router_result.request_type.value,
    )
    db.add(assistant_msg)

    await db.commit()

    return MessageResponse(
        response=llm_result["response"],
        tokens_used=tokens_total,
        response_time_ms=elapsed_ms,
        domain=llm_result["domain"],
        model=llm_result["model"],
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
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


# ---------------------------------------------------------------------------
# GET /pool/stats (диагностика)
# ---------------------------------------------------------------------------

@router.get("/pool/stats")
async def get_pool_stats(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Возвращает статус пула аккаунтов GigaChat (для мониторинга)."""
    return pool.get_stats()
