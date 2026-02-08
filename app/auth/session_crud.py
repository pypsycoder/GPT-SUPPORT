"""CRUD operations for sessions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Session


async def create_session(
    session: AsyncSession,
    token: str,
    user_id: Optional[int] = None,
    researcher_id: Optional[int] = None,
    expires_at: Optional[datetime] = None,
    user_agent: Optional[str] = None,
) -> Session:
    """Create a new session."""
    if user_id is None and researcher_id is None:
        raise ValueError("Either user_id or researcher_id must be provided")

    if user_id is not None and researcher_id is not None:
        raise ValueError("Only one of user_id or researcher_id should be provided")

    db_session = Session(
        token=token,
        user_id=user_id,
        researcher_id=researcher_id,
        expires_at=expires_at,
        user_agent=user_agent,
    )
    session.add(db_session)
    await session.commit()
    await session.refresh(db_session)
    return db_session


async def get_session(session: AsyncSession, token: str) -> Optional[Session]:
    """Get a session by token."""
    result = await session.execute(select(Session).where(Session.token == token))
    db_session = result.scalar_one_or_none()

    if db_session is None:
        return None

    if db_session.is_expired():
        await delete_session(session, token)
        return None

    return db_session


async def delete_session(session: AsyncSession, token: str) -> bool:
    """
    Delete a session by token.

    Args:
        session: Database session
        token: Session token

    Returns:
        True if session was deleted, False if not found
    """
    result = await session.execute(delete(Session).where(Session.token == token))
    await session.commit()
    return result.rowcount > 0


async def delete_user_sessions(session: AsyncSession, user_id: int) -> int:
    """
    Delete all sessions for a user (logout from all devices).

    Args:
        session: Database session
        user_id: Patient user ID

    Returns:
        Number of deleted sessions
    """
    result = await session.execute(delete(Session).where(Session.user_id == user_id))
    await session.commit()
    return result.rowcount


async def delete_researcher_sessions(session: AsyncSession, researcher_id: int) -> int:
    """
    Delete all sessions for a researcher (logout from all devices).

    Args:
        session: Database session
        researcher_id: Researcher ID

    Returns:
        Number of deleted sessions
    """
    result = await session.execute(
        delete(Session).where(Session.researcher_id == researcher_id)
    )
    await session.commit()
    return result.rowcount


async def delete_expired_sessions(session: AsyncSession) -> int:
    """
    Delete all expired sessions (cleanup task).

    Args:
        session: Database session

    Returns:
        Number of deleted sessions
    """
    result = await session.execute(
        delete(Session).where(Session.expires_at <= datetime.now(timezone.utc))
    )
    await session.commit()
    return result.rowcount


async def get_user_sessions(session: AsyncSession, user_id: int) -> list[Session]:
    """
    Get all active sessions for a user.

    Args:
        session: Database session
        user_id: Patient user ID

    Returns:
        List of active Session objects
    """
    result = await session.execute(
        select(Session)
        .where(Session.user_id == user_id)
        .where(Session.expires_at > datetime.now(timezone.utc))
    )
    return result.scalars().all()


async def get_researcher_sessions(session: AsyncSession, researcher_id: int) -> list[Session]:
    """
    Get all active sessions for a researcher.

    Args:
        session: Database session
        researcher_id: Researcher ID

    Returns:
        List of active Session objects
    """
    result = await session.execute(
        select(Session)
        .where(Session.researcher_id == researcher_id)
        .where(Session.expires_at > datetime.now(timezone.utc))
    )
    return result.scalars().all()
