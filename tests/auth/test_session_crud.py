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
from app.auth.session_crud import create_session, delete_session, get_session  # noqa: E402
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
