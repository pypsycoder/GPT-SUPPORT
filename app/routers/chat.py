"""
Chat HTTP router for patient <-> LLM interaction.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.llm.pipeline import LLMPipeline, LLMRequest
from app.llm.pool import pool
from app.llm.router import classify_request
from app.models.llm import ChatMessage
from app.users.models import User
from core.db.session import get_async_session

router = APIRouter()
_llm_pipeline = LLMPipeline()


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
    created_at: str

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


@router.post("/message", response_model=MessageResponse)
async def send_message(
    body: MessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> MessageResponse:
    if current_user.id != body.patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к чату другого пациента",
        )

    router_result = classify_request(body.message, body.source)
    llm_response = await _llm_pipeline.process(
        LLMRequest(
            patient_id=body.patient_id,
            user_input=body.message,
            source=body.source,
            router_result=router_result,
            db=db,
        )
    )
    tokens_total = llm_response.tokens_input + llm_response.tokens_output

    db.add(
        ChatMessage(
            patient_id=body.patient_id,
            role="user",
            content=body.message,
            tokens_used=0,
            model_used=None,
            domain=llm_response.domain,
            request_type=router_result.request_type.value,
        )
    )
    db.add(
        ChatMessage(
            patient_id=body.patient_id,
            role="assistant",
            content=llm_response.response,
            tokens_used=tokens_total,
            model_used=llm_response.model,
            domain=llm_response.domain,
            request_type=router_result.request_type.value,
        )
    )
    await db.commit()

    return MessageResponse(
        response=llm_response.response,
        tokens_used=tokens_total,
        response_time_ms=llm_response.response_time_ms,
        domain=llm_response.domain,
        model=llm_response.model,
        pending_vitals=llm_response.pending_vitals,
    )


@router.get("/history/{patient_id}", response_model=list[ChatMessageOut])
async def get_history(
    patient_id: int,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[ChatMessageOut]:
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


@router.get("/pool/stats")
async def get_pool_stats(current_user: User = Depends(get_current_user)) -> dict:
    return pool.get_stats()
