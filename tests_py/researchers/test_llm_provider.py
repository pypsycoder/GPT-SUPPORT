from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api_errors import register_api_exception_handlers
from app.auth.dependencies import get_current_researcher
from app.core.app_settings import LLM_PROVIDER_KEY
from app.llm.pool import AccountPool
from app.models.app_settings import AppSetting
from app.researchers.models import Researcher
from app.researchers.router import router as researcher_router
from core.db.session import get_async_session
from tests_py.sqlite_schema import create_tables


@asynccontextmanager
async def _session_ctx():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "public": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables, Researcher, AppSetting)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _pool_with_both_keys(monkeypatch) -> AccountPool:
    for name in ("GIGACHAT_KEY_A1", "CLOUD_RU_KEY"):
        monkeypatch.setenv(name, "sber-key" if "GIGA" in name else "keyid.secret")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    pool = AccountPool()
    monkeypatch.setattr("app.researchers.router._llm_pool", pool)
    return pool


def _client(session, researcher):
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    app = FastAPI()
    register_api_exception_handlers(app)
    app.include_router(researcher_router, prefix="/api/v1")

    async def _sess():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_async_session] = _sess
    app.dependency_overrides[get_current_researcher] = lambda: researcher
    return TestClient(app)


def test_get_returns_env_default_when_db_empty(monkeypatch):
    async def runner():
        pool = _pool_with_both_keys(monkeypatch)
        async with _session_ctx() as seed:
            researcher = Researcher(username="r1", password_hash="x")
            seed.add(researcher)
            await seed.commit()
            await seed.refresh(researcher)

            client = _client(seed, researcher)
            body = client.get("/api/v1/researcher/llm-provider").json()

        assert body["active"] == "sber"
        assert body["env_default"] == "sber"
        assert body["db_override"] is None
        assert set(body["configured"]) == {"sber", "cloudru"}
        assert pool.chat_provider == "sber"

    asyncio.run(runner())


def test_post_switches_provider_and_persists(monkeypatch):
    async def runner():
        pool = _pool_with_both_keys(monkeypatch)
        async with _session_ctx() as seed:
            researcher = Researcher(username="switcher", password_hash="x")
            seed.add(researcher)
            await seed.commit()
            await seed.refresh(researcher)

            client = _client(seed, researcher)
            resp = client.post("/api/v1/researcher/llm-provider", json={"provider": "cloudru"})
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["active"] == "cloudru"
            assert body["db_override"] == "cloudru"
            assert body["updated_by"] == "switcher"

            # пул переключён здесь и сейчас
            assert pool.chat_provider == "cloudru"
            # значение легло в app_settings — переживёт рестарт
            row = await seed.get(AppSetting, LLM_PROVIDER_KEY)
            assert row is not None and row.value == "cloudru"

    asyncio.run(runner())


def test_post_rejects_provider_without_key(monkeypatch):
    async def runner():
        monkeypatch.setenv("GIGACHAT_KEY_A1", "sber-key")
        monkeypatch.delenv("CLOUD_RU_KEY", raising=False)
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.setattr("app.researchers.router._llm_pool", AccountPool())

        async with _session_ctx() as seed:
            researcher = Researcher(username="r", password_hash="x")
            seed.add(researcher)
            await seed.commit()
            await seed.refresh(researcher)

            client = _client(seed, researcher)
            resp = client.post("/api/v1/researcher/llm-provider", json={"provider": "cloudru"})
            assert resp.status_code == 400
            assert "cloudru" in resp.json()["detail"]

    asyncio.run(runner())
