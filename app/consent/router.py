# ============================================
# Consent Router: Эндпоинты согласий пациента
# ============================================
# GET — статус согласия, POST — принятие согласия.

"""API endpoints for patient consent management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.session import get_async_session
from app.auth.dependencies import get_current_user
from app.consent.schemas import ConsentStatus, ConsentAcceptRequest, ConsentRevokeRequest
from app.consent.service import get_consent_status, accept_consent, revoke_consent
from app.users.models import User

router = APIRouter(prefix="/consent", tags=["consent"])


@router.get("/status", response_model=ConsentStatus)
async def consent_status(user: User = Depends(get_current_user)):
    """Return current consent status for the authenticated patient."""
    return await get_consent_status(user)


@router.post("/accept", response_model=ConsentStatus)
async def consent_accept(
    body: ConsentAcceptRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Accept consent for the authenticated patient."""
    import logging
    logger = logging.getLogger("gpt-support-consent")
    logger.info(f"[consent] POST /accept called for user {user.id}")
    logger.info(f"[consent] Body: {body}")
    
    user = await accept_consent(
        session,
        user,
        consent_personal_data=body.consent_personal_data,
        consent_bot_use=body.consent_bot_use,
    )
    logger.info(f"[consent] User {user.id} consent accepted, returning status")
    return await get_consent_status(user)


@router.post("/revoke", response_model=ConsentStatus)
async def consent_revoke(
    body: ConsentRevokeRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Отозвать согласия для авторизованного пациента."""
    if not body.revoke_personal_data and not body.revoke_bot_use:
        raise HTTPException(
            status_code=400,
            detail="Укажите хотя бы одно согласие для отзыва (revoke_personal_data или revoke_bot_use).",
        )
    user = await revoke_consent(
        session,
        user,
        revoke_personal_data=body.revoke_personal_data,
        revoke_bot_use=body.revoke_bot_use,
    )
    return await get_consent_status(user)
