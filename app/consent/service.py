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
    session.add(user)
    await session.commit()
    logger.info("[consent] user %s accepted consent", user.id)
    return user
