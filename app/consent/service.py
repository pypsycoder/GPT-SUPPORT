# ============================================
# Consent Service: Логика согласий пациента
# ============================================
# Проверка статуса и принятие согласий на обработку ПДн.

"""Business logic for patient consent management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User

logger = logging.getLogger("gpt-support-consent")


async def get_consent_status(user: User) -> dict:
    """Return current consent status for a patient."""
    needs = not user.consent_personal_data
    return {
        "consent_personal_data": user.consent_personal_data,
        "consent_bot_use": user.consent_bot_use,
        "consent_given_at": user.consent_given_at,
        "needs_consent": needs,
    }


async def accept_consent(
    session: AsyncSession,
    user: User,
    *,
    consent_personal_data: bool = True,
    consent_bot_use: bool = True,
) -> User:
    """Record that the patient has given consent."""
    user.consent_personal_data = consent_personal_data
    user.consent_bot_use = consent_bot_use
    user.consent_given_at = datetime.now(timezone.utc)
    # Note: user is already tracked by the session, no need to add
    await session.commit()
    logger.info("[consent] user %s accepted consent", user.id)
    return user


async def revoke_consent(
    session: AsyncSession,
    user: User,
    *,
    revoke_personal_data: bool = False,
    revoke_bot_use: bool = False,
) -> User:
    """Отозвать указанные согласия пациента."""
    if revoke_personal_data:
        user.consent_personal_data = False
    if revoke_bot_use:
        user.consent_bot_use = False
    if revoke_personal_data and revoke_bot_use:
        user.consent_given_at = None
    elif revoke_personal_data or revoke_bot_use:
        # При частичном отзыве дату не сбрасываем (остаётся момент последнего принятия)
        pass
    await session.commit()
    logger.info(
        "[consent] user %s revoked consent: personal_data=%s, bot_use=%s",
        user.id, revoke_personal_data, revoke_bot_use,
    )
    return user
