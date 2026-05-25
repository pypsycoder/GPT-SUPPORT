from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.auth.models import Session  # noqa: E402
from app.auth.session_crud import (  # noqa: E402
    cleanup_sessions,
    create_session,
    delete_session,
    get_session,
    revoke_session,
    touch_session,
)
from app.users.models import User  # noqa: E402


@asynccontextmanager
async def session_ctx() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(Session.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def create_user(session: AsyncSession) -> User:
    user = User(
        telegram_id="98765",
        full_name="Auth Test User",
        consent_personal_data=True,
        consent_bot_use=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


def test_session_token_is_hashed_and_resolvable():
    async def runner():
        async with session_ctx() as session:
            user = await create_user(session)
            raw_token = "plain-session-token"

            created = await create_session(
                session,
                token=raw_token,
                user_id=user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )

            assert created.token != raw_token
            assert len(created.token) == 64

            resolved = await get_session(session, raw_token)
            assert resolved is not None
            assert resolved.user_id == user.id

    asyncio.run(runner())


def test_delete_session_accepts_raw_token():
    async def runner():
        async with session_ctx() as session:
            user = await create_user(session)
            raw_token = "delete-me-token"

            await create_session(
                session,
                token=raw_token,
                user_id=user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )

            deleted = await delete_session(session, raw_token)
            assert deleted is True

            result = await session.execute(select(Session))
            assert result.scalar_one_or_none() is None
            assert await get_session(session, raw_token) is None

    asyncio.run(runner())


def test_revoked_session_is_not_resolvable_and_is_cleaned_up():
    async def runner():
        async with session_ctx() as session:
            user = await create_user(session)
            raw_token = "revoked-token"

            created = await create_session(
                session,
                token=raw_token,
                user_id=user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
            assert created.revoked_at is None

            revoked = await revoke_session(session, raw_token, reason="test")
            assert revoked is True

            assert await get_session(session, raw_token) is None
            cleaned = await cleanup_sessions(session)
            assert cleaned == 0

    asyncio.run(runner())


def test_touch_session_updates_last_seen_and_last_seen_ip():
    async def runner():
        async with session_ctx() as session:
            user = await create_user(session)
            raw_token = "touch-me"

            created = await create_session(
                session,
                token=raw_token,
                user_id=user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                ip_address="127.0.0.1",
            )
            original_last_seen = created.last_seen_at

            created.last_seen_at = created.last_seen_at - timedelta(minutes=10)
            await session.commit()

            touched = await touch_session(
                session,
                created,
                user_agent="pytest-agent",
                ip_address="10.0.0.5",
            )

            assert touched.last_seen_at > original_last_seen - timedelta(minutes=5)
            assert touched.last_seen_ip == "10.0.0.5"
            assert touched.user_agent == "pytest-agent"

    asyncio.run(runner())
