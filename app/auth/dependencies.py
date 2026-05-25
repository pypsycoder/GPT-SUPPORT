# ============================================
# Auth Dependencies: Извлечение текущего пользователя
# ============================================
# FastAPI Depends для получения User/Researcher из session cookie.

"""FastAPI dependencies for authentication — extract current user/researcher from session cookies."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.session import get_async_session
from app.users.models import User
from app.researchers.models import Researcher
from app.auth.session_crud import get_session

logger = logging.getLogger("gpt-support-auth")


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_current_user_optional(
    request: Request,
    patient_session: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(get_async_session),
) -> Optional[User]:
    """Return the authenticated patient or *None*."""
    if not patient_session:
        return None

    db_session = await get_session(
        session,
        patient_session,
        touch=True,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    if db_session is None:
        logger.info("[auth] patient session not found or expired")
        return None

    if db_session.user_id is None:
        logger.warning("[auth] patient cookie points to non-patient session")
        return None

    result = await session.execute(select(User).where(User.id == db_session.user_id))
    return result.scalar_one_or_none()


async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """Return the authenticated patient or raise 401."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не авторизован",
        )
    return user


async def get_current_researcher_optional(
    request: Request,
    researcher_session: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(get_async_session),
) -> Optional[Researcher]:
    """Return the authenticated researcher or *None*."""
    if not researcher_session:
        return None
    
    db_session = await get_session(
        session,
        researcher_session,
        touch=True,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    if db_session is None:
        return None

    if db_session.researcher_id is None:
        return None

    result = await session.execute(
        select(Researcher).where(Researcher.id == db_session.researcher_id)
    )
    return result.scalar_one_or_none()


async def get_current_researcher(
    researcher: Optional[Researcher] = Depends(get_current_researcher_optional),
) -> Researcher:
    """Return the authenticated researcher or raise 401."""
    if researcher is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не авторизован",
        )
    return researcher
