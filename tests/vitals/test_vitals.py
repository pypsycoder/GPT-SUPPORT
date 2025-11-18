from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.models import Base  # noqa: E402
from app.users.models import User  # noqa: E402
from app.vitals.crud import bp_crud  # noqa: E402
from app.vitals.service import VitalsService  # noqa: E402


@asynccontextmanager
async def session_ctx() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"vitals": None, "users": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def create_user(session: AsyncSession) -> User:
    user = User(
        telegram_id="12345",
        full_name="Test User",
        consent_personal_data=True,
        consent_bot_use=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


def test_create_bp():
    async def runner():
        async with session_ctx() as session:
            user = await create_user(session)
            measurement = await bp_crud.create(
                session,
                VitalsService.prepare_bp_data(
                    user_id=user.id,
                    systolic=120,
                    diastolic=80,
                    measured_at=datetime.now(timezone.utc),
                ),
            )
            await session.commit()
            assert measurement.id is not None
            assert measurement.systolic == 120
            assert measurement.diastolic == 80

    asyncio.run(runner())


def test_filter_by_date():
    async def runner():
        async with session_ctx() as session:
            user = await create_user(session)
            now = datetime.now(timezone.utc)
            earlier = now - timedelta(days=2)
            later = now + timedelta(days=2)

            for moment in (earlier, now, later):
                await bp_crud.create(
                    session,
                    VitalsService.prepare_bp_data(
                        user_id=user.id, systolic=110, diastolic=70, measured_at=moment
                    ),
                )
            await session.commit()

            records = await bp_crud.list(
                session,
                user_id=user.id,
                date_from=now - timedelta(days=1),
                date_to=now + timedelta(days=1),
            )
            assert len(records) == 1
            assert records[0].measured_at.replace(tzinfo=timezone.utc) == now

    asyncio.run(runner())


def test_ordering():
    async def runner():
        async with session_ctx() as session:
            user = await create_user(session)
            first = datetime(2023, 1, 1, tzinfo=timezone.utc)
            second = datetime(2023, 1, 2, tzinfo=timezone.utc)

            await bp_crud.create(
                session,
                VitalsService.prepare_bp_data(
                    user_id=user.id, systolic=115, diastolic=75, measured_at=first
                ),
            )
            await bp_crud.create(
                session,
                VitalsService.prepare_bp_data(
                    user_id=user.id, systolic=118, diastolic=78, measured_at=second
                ),
            )
            await session.commit()

            records = await bp_crud.list(session, user_id=user.id)
            assert len(records) == 2
            assert records[0].measured_at == second

    asyncio.run(runner())


def test_invalid_values():
    async def runner():
        async with session_ctx() as session:
            user = await create_user(session)
            try:
                VitalsService.prepare_bp_data(user_id=user.id, systolic=20, diastolic=80)
            except ValueError:
                return
            assert False, "Expected ValueError for invalid blood pressure"

    asyncio.run(runner())
