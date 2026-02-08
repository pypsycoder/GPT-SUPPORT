"""CRUD operations for researcher-managed patients."""

from __future__ import annotations

import logging
import secrets
from typing import Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User
from app.researchers.models import Researcher
from app.auth.security import hash_pin, generate_pin, hash_password
from app.users.utils import generate_patient_token

logger = logging.getLogger("gpt-support-researcher")


# ---------------------------------------------------------------------------
# Patient number generation
# ---------------------------------------------------------------------------

async def _generate_unique_patient_number(session: AsyncSession) -> int:
    """Generate a unique 4-digit patient number (1000–9999)."""
    for _ in range(100):  # safety limit
        number = secrets.randbelow(9000) + 1000
        exists = await session.execute(
            select(User.id).where(User.patient_number == number)
        )
        if exists.scalar_one_or_none() is None:
            return number
    raise RuntimeError("Не удалось сгенерировать уникальный номер пациента")


# ---------------------------------------------------------------------------
# Patient CRUD
# ---------------------------------------------------------------------------

async def create_patient(
    session: AsyncSession,
    *,
    full_name: str,
    age: Optional[int] = None,
    gender: Optional[str] = None,
) -> tuple[User, str]:
    """Create a new patient with generated number and PIN.

    Returns ``(user, plaintext_pin)``.
    """
    patient_number = await _generate_unique_patient_number(session)
    pin = generate_pin(4)
    pin_hashed = hash_pin(pin)

    user = User(
        full_name=full_name,
        age=age,
        gender=gender,
        patient_number=patient_number,
        pin_hash=pin_hashed,
        patient_token=generate_patient_token(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info(
        "[researcher] created patient id=%s, number=%s",
        user.id,
        patient_number,
    )
    return user, pin


async def list_patients(session: AsyncSession) -> Sequence[User]:
    """Return all patients ordered by id desc."""
    result = await session.execute(
        select(User).order_by(User.id.desc())
    )
    return result.scalars().all()


async def get_patient_by_id(
    session: AsyncSession,
    patient_id: int,
) -> Optional[User]:
    result = await session.execute(
        select(User).where(User.id == patient_id)
    )
    return result.scalar_one_or_none()


async def reset_patient_pin(
    session: AsyncSession,
    user: User,
) -> str:
    """Generate a new PIN for the patient. Returns plaintext PIN."""
    pin = generate_pin(4)
    user.pin_hash = hash_pin(pin)
    user.pin_attempts = 0
    user.is_locked = False
    await session.commit()
    await session.refresh(user)
    logger.info("[researcher] reset PIN for patient id=%s", user.id)
    return pin


async def unlock_patient(
    session: AsyncSession,
    user: User,
) -> User:
    """Unlock a locked patient account."""
    user.is_locked = False
    user.pin_attempts = 0
    await session.commit()
    await session.refresh(user)
    logger.info("[researcher] unlocked patient id=%s", user.id)
    return user


# ---------------------------------------------------------------------------
# Researcher CRUD
# ---------------------------------------------------------------------------

async def get_researcher_by_username(
    session: AsyncSession,
    username: str,
) -> Optional[Researcher]:
    result = await session.execute(
        select(Researcher).where(Researcher.username == username)
    )
    return result.scalar_one_or_none()


async def create_researcher(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    full_name: Optional[str] = None,
) -> Researcher:
    """Create a new researcher account."""
    researcher = Researcher(
        username=username,
        password_hash=hash_password(password),
        full_name=full_name,
    )
    session.add(researcher)
    await session.commit()
    await session.refresh(researcher)
    logger.info("[researcher] created researcher id=%s, username=%s", researcher.id, username)
    return researcher


async def get_patients_stats(session: AsyncSession) -> dict:
    """Return basic patient statistics for the dashboard."""
    total = await session.execute(select(func.count(User.id)))
    locked = await session.execute(
        select(func.count(User.id)).where(User.is_locked == True)  # noqa: E712
    )
    consented = await session.execute(
        select(func.count(User.id)).where(User.consent_personal_data == True)  # noqa: E712
    )
    return {
        "total_patients": total.scalar_one(),
        "locked_patients": locked.scalar_one(),
        "consented_patients": consented.scalar_one(),
    }
