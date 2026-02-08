"""Authentication business logic for patients and researchers."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import verify_pin, verify_password
from app.users.models import User
from app.researchers.models import Researcher

logger = logging.getLogger("gpt-support-auth")

MAX_PIN_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Patient authentication
# ---------------------------------------------------------------------------

async def authenticate_patient(
    session: AsyncSession,
    *,
    patient_number: int,
    pin: str,
) -> tuple[Optional[User], str]:
    """Verify patient credentials.

    Returns ``(user, error_message)``.
    On success *error_message* is an empty string.
    """
    stmt = select(User).where(User.patient_number == patient_number)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        logger.warning("[auth] patient_number=%s not found", patient_number)
        return None, "Неверный номер пациента или PIN"

    if user.is_locked:
        logger.warning("[auth] patient_number=%s is locked", patient_number)
        return None, "Аккаунт заблокирован. Обратитесь к исследователю"

    if not user.pin_hash:
        logger.error("[auth] patient_number=%s has no pin_hash", patient_number)
        return None, "Неверный номер пациента или PIN"

    if not verify_pin(pin, user.pin_hash):
        user.pin_attempts = (user.pin_attempts or 0) + 1
        if user.pin_attempts >= MAX_PIN_ATTEMPTS:
            user.is_locked = True
            logger.warning(
                "[auth] patient_number=%s LOCKED after %d attempts",
                patient_number,
                user.pin_attempts,
            )
        await session.commit()
        remaining = MAX_PIN_ATTEMPTS - user.pin_attempts
        if user.is_locked:
            return None, "Аккаунт заблокирован. Обратитесь к исследователю"
        return None, f"Неверный номер пациента или PIN (осталось попыток: {remaining})"

    # success — reset attempts
    if user.pin_attempts > 0:
        user.pin_attempts = 0
        await session.commit()

    logger.info("[auth] patient_number=%s logged in", patient_number)
    return user, ""


# ---------------------------------------------------------------------------
# Researcher authentication
# ---------------------------------------------------------------------------

async def authenticate_researcher(
    session: AsyncSession,
    *,
    username: str,
    password: str,
) -> tuple[Optional[Researcher], str]:
    """Verify researcher credentials.

    Returns ``(researcher, error_message)``.
    """
    stmt = select(Researcher).where(Researcher.username == username)
    result = await session.execute(stmt)
    researcher = result.scalar_one_or_none()

    if researcher is None:
        logger.warning("[auth] researcher username=%s not found", username)
        return None, "Неверный логин или пароль"

    if not researcher.is_active:
        return None, "Аккаунт деактивирован"

    if not verify_password(password, researcher.password_hash):
        logger.warning("[auth] researcher username=%s wrong password", username)
        return None, "Неверный логин или пароль"

    logger.info("[auth] researcher username=%s logged in", username)
    return researcher, ""
