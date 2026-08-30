"""Триггер проактива при входе: фон после логина + ленивый вызов из истории чата."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.auth.router as auth_router_mod
import app.routers.chat as chat_router_mod
from app.api import API_V1_PREFIX
from app.api_errors import register_api_exception_handlers
from app.auth.dependencies import get_current_user
from app.auth.models import Session
from app.auth.router import router as auth_router
from app.auth.security import hash_pin
from app.models.llm import ChatMessage, ChatSupervisorState
from app.researchers.models import Researcher
from app.routers.chat import router as chat_router
from app.users.models import User
from core.db.session import get_async_session
from tests_py.sqlite_schema import create_tables


@asynccontextmanager
async def _sqlite_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables, User, Researcher, Session, ChatMessage, ChatSupervisorState)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _seed_patient(session: AsyncSession, **overrides) -> User:
    fields = dict(
        full_name="Patient Trigger",
        patient_number=7010,
        pin_hash=hash_pin("1234"),
        consent_personal_data=True,
        consent_bot_use=True,
        is_onboarded=True,
    )
    fields.update(overrides)
    user = User(**fields)
    session.add(user)
    return user


# ── Логин ────────────────────────────────────────────────────────────────────

def _run_login_case(*, seed_overrides: dict, expect_scheduled: bool):
    async def runner():
        async with _sqlite_session() as seed_session:
            user = _seed_patient(seed_session, **seed_overrides)
            await seed_session.commit()
            await seed_session.refresh(user)

            factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = FastAPI()
            register_api_exception_handlers(app)
            app.include_router(auth_router, prefix=API_V1_PREFIX)

            async def override_session():
                async with factory() as session:
                    yield session

            app.dependency_overrides[get_async_session] = override_session

            spy = AsyncMock()
            # monkeypatch без фикстуры — правим модульный атрибут вручную
            original = auth_router_mod.run_login_proactive
            auth_router_mod.run_login_proactive = spy
            try:
                with TestClient(app) as client:
                    resp = client.post(
                        f"{API_V1_PREFIX}/auth/patient/login",
                        json={"patient_number": user.patient_number, "pin": "1234"},
                    )
            finally:
                auth_router_mod.run_login_proactive = original

            assert resp.status_code == 200
            if expect_scheduled:
                spy.assert_awaited_once_with(user.id)
            else:
                spy.assert_not_awaited()

    asyncio.run(runner())


def test_login_schedules_proactive_for_eligible_patient():
    _run_login_case(seed_overrides={}, expect_scheduled=True)


def test_login_skips_proactive_when_onboarding_pending():
    _run_login_case(seed_overrides={"is_onboarded": False}, expect_scheduled=False)


def test_login_skips_proactive_when_consent_missing():
    _run_login_case(
        seed_overrides={"consent_personal_data": False},
        expect_scheduled=False,
    )


# ── История чата ─────────────────────────────────────────────────────────────

def test_chat_history_schedules_proactive():
    async def runner():
        async with _sqlite_session() as seed_session:
            user = _seed_patient(seed_session)
            await seed_session.commit()
            await seed_session.refresh(user)

            factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = FastAPI()
            app.include_router(chat_router, prefix="/api/chat")

            async def override_session():
                async with factory() as session:
                    yield session

            async def override_user() -> User:
                return user

            app.dependency_overrides[get_async_session] = override_session
            app.dependency_overrides[get_current_user] = override_user

            spy = AsyncMock()
            original = chat_router_mod.run_login_proactive
            chat_router_mod.run_login_proactive = spy
            try:
                with TestClient(app) as client:
                    resp = client.get(f"/api/chat/history/{user.id}")
            finally:
                chat_router_mod.run_login_proactive = original

            assert resp.status_code == 200
            spy.assert_awaited_once_with(user.id)

    asyncio.run(runner())
