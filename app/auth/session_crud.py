# ============================================
# Session CRUD: Управление сессиями авторизации
# ============================================
# Создание, поиск, удаление и валидация сессий
# для пациентов и исследователей (token-based).

"""CRUD operations for sessions."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Session
from app.auth.session_policy import SESSION_TOUCH_INTERVAL


def _hash_token(token: str) -> str:
    """Return a stable SHA-256 hash for a session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_dt(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def create_session(
    session: AsyncSession,
    token: str,
    user_id: Optional[int] = None,
    researcher_id: Optional[int] = None,
    expires_at: Optional[datetime] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Session:
    """Create a new session."""
    if user_id is None and researcher_id is None:
        raise ValueError("Either user_id or researcher_id must be provided")

    if user_id is not None and researcher_id is not None:
        raise ValueError("Only one of user_id or researcher_id should be provided")

    db_session = Session(
        token=_hash_token(token),
        user_id=user_id,
        researcher_id=researcher_id,
        expires_at=_normalize_dt(expires_at),
        user_agent=user_agent,
        ip_address=ip_address,
        last_seen_ip=ip_address,
    )
    session.add(db_session)
    await session.commit()
    await session.refresh(db_session)
    return db_session


async def touch_session(
    session: AsyncSession,
    db_session: Session,
    *,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Session:
    now = _utcnow()
    last_seen_at = _normalize_dt(db_session.last_seen_at) or now
    should_commit = db_session.last_seen_at is None or now - last_seen_at >= SESSION_TOUCH_INTERVAL

    if user_agent and db_session.user_agent != user_agent:
        db_session.user_agent = user_agent
        should_commit = True

    if ip_address and db_session.last_seen_ip != ip_address:
        db_session.last_seen_ip = ip_address
        should_commit = True

    if should_commit:
        db_session.last_seen_at = now
        await session.commit()
        await session.refresh(db_session)

    return db_session


async def get_session(
    session: AsyncSession,
    token: str,
    *,
    touch: bool = False,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Optional[Session]:
    """Get a session by token."""
    token_hash = _hash_token(token)
    result = await session.execute(
        select(Session).where(Session.token.in_([token_hash, token]))
    )
    db_session = result.scalar_one_or_none()

    if db_session is None:
        return None

    if db_session.is_expired() or db_session.is_revoked():
        await delete_session(session, token)
        return None

    if touch:
        await touch_session(
            session,
            db_session,
            user_agent=user_agent,
            ip_address=ip_address,
        )

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
    token_hash = _hash_token(token)
    result = await session.execute(
        delete(Session).where(Session.token.in_([token_hash, token]))
    )
    await session.commit()
    return result.rowcount > 0


async def revoke_session(session: AsyncSession, token: str, *, reason: str = "logout") -> bool:
    token_hash = _hash_token(token)
    result = await session.execute(
        select(Session).where(Session.token.in_([token_hash, token]))
    )
    db_session = result.scalar_one_or_none()
    if db_session is None:
        return False

    db_session.revoked_at = _utcnow()
    db_session.revoked_reason = reason
    await session.commit()
    return True


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


async def revoke_user_sessions(
    session: AsyncSession,
    user_id: int,
    *,
    reason: str = "rotated",
) -> int:
    result = await session.execute(select(Session).where(Session.user_id == user_id))
    db_sessions = result.scalars().all()
    now = _utcnow()
    updated = 0
    for db_session in db_sessions:
        if db_session.revoked_at is None:
            db_session.revoked_at = now
            db_session.revoked_reason = reason
            updated += 1
    await session.commit()
    return updated


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


async def revoke_researcher_sessions(
    session: AsyncSession,
    researcher_id: int,
    *,
    reason: str = "rotated",
) -> int:
    result = await session.execute(
        select(Session).where(Session.researcher_id == researcher_id)
    )
    db_sessions = result.scalars().all()
    now = _utcnow()
    updated = 0
    for db_session in db_sessions:
        if db_session.revoked_at is None:
            db_session.revoked_at = now
            db_session.revoked_reason = reason
            updated += 1
    await session.commit()
    return updated


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


async def cleanup_sessions(session: AsyncSession) -> int:
    """Delete expired or revoked sessions in one sweep."""
    result = await session.execute(
        delete(Session).where(
            or_(
                Session.expires_at <= _utcnow(),
                Session.revoked_at.is_not(None),
            )
        )
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
