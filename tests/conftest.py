"""Common pytest fixtures for integration tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


# --- Environment bootstrap -------------------------------------------------

# Ensure the project root is importable so ``app`` package can be resolved in tests.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load variables from the .env file specified in ENV_FILE (defaults to ".env.test").
ENV_PATH = Path(os.getenv("ENV_FILE", ".env.test"))
load_dotenv(ENV_PATH)


def _get_required_env(name: str) -> str:
    """Fetch a required environment variable and fail fast when it is missing."""

    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} must be set for tests")
    return value


# --- Alembic migrations -----------------------------------------------------
@pytest.fixture(scope="session")
def alembic_upgrade() -> None:
    """Apply all Alembic migrations once before the test session starts."""

    database_url = _get_required_env("DATABASE_URL")

    # ⬇️ NEW: Alembic нужен синхронный драйвер
    sync_url = (
        database_url.replace("+asyncpg", "+psycopg")
        if "+asyncpg" in database_url
        else database_url
    )

    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    sync_url = (
        database_url.replace("+asyncpg", "+psycopg")
        if "+asyncpg" in database_url else database_url
    )
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)  # ⬅️ было: database_url
    alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))

    command.upgrade(alembic_cfg, "head")


# --- Async SQLAlchemy session ----------------------------------------------

@pytest.fixture
async def async_session(alembic_upgrade: None) -> AsyncIterator[AsyncSession]:
    """Provide a transactional async session with automatic rollback per test."""

    database_url = _get_required_env("APP_DATABASE_URL")
    engine: AsyncEngine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.connect() as connection:
        # Start an explicit transaction and a savepoint so every test can rollback safely.
        transaction = await connection.begin()
        async with session_factory(bind=connection) as session:
            await connection.begin_nested()

            # Re-create the savepoint whenever SQLAlchemy ends the nested transaction.
            @event.listens_for(session.sync_session, "after_transaction_end")
            def restart_savepoint(sess, trans) -> None:  # type: ignore[override]
                if trans.nested and not trans._parent.nested:  # pragma: no cover - SQLAlchemy internals
                    sess.connection().sync_connection.begin_nested()

            try:
                yield session
            finally:
                # Remove the event listener to avoid leaking handlers between tests.
                event.remove(session.sync_session, "after_transaction_end", restart_savepoint)

        # Roll back everything done inside the outer transaction so the DB stays clean.
        await transaction.rollback()

    # Close all underlying connections.
    await engine.dispose()
