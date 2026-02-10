# ============================================
# Auth Dependencies: Извлечение текущего пользователя
# ============================================
# FastAPI Depends для получения User/Researcher из session cookie.

"""FastAPI dependencies for authentication — extract current user/researcher from session cookies."""

from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.session import get_async_session
from app.users.models import User
from app.researchers.models import Researcher
from app.auth.session_crud import get_session


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_current_user_optional(
    patient_session: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(get_async_session),
) -> Optional[User]:
    """Return the authenticated patient or *None*."""
    import logging
    logger = logging.getLogger("gpt-support-auth")
    
    logger.info(f"[auth] get_current_user_optional called")
    logger.info(f"[auth] patient_session cookie: {patient_session[:20] if patient_session else 'None'}...")
    
    if not patient_session:
        logger.warning("[auth] No patient_session cookie!")
        return None
    
    # Get session from database
    db_session = await get_session(session, patient_session)
    if db_session is None:
        logger.warning(f"[auth] Session token not found in database or expired!")
        return None
    
    if db_session.user_id is None:
        logger.warning(f"[auth] Session is for researcher, not patient!")
        return None
    
    # Get user from database
    result = await session.execute(select(User).where(User.id == db_session.user_id))
    user = result.scalar_one_or_none()
    logger.info(f"[auth] Found user: {user.id if user else 'None'}")
    return user


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
    researcher_session: Optional[str] = Cookie(None),
    session: AsyncSession = Depends(get_async_session),
) -> Optional[Researcher]:
    """Return the authenticated researcher or *None*."""
    if not researcher_session:
        return None
    
    # Get session from database
    db_session = await get_session(session, researcher_session)
    if db_session is None:
        return None
    
    if db_session.researcher_id is None:
        return None
    
    # Get researcher from database
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
