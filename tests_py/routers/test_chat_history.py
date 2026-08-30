"""GET /api/chat/history — payload сообщений (в т.ч. inline-кнопки)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.dependencies import get_current_user
from app.models.llm import ChatMessage, ChatSupervisorState
from app.routers.chat import router as chat_router
from app.users.models import User
from core.db.session import get_async_session
from tests_py.sqlite_schema import create_tables


@asynccontextmanager
async def _ctx() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables, User, ChatMessage, ChatSupervisorState)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def test_history_returns_buttons_json_so_frontend_can_re_render_them():
    async def runner():
        async with _ctx() as seed:
            patient = User(full_name="Patient Hist", patient_number=4100)
            seed.add(patient)
            await seed.commit()
            await seed.refresh(patient)

            buttons = [{"label": "Внести данные о сне", "action": "open_sleep"}]
            seed.add_all([
                ChatMessage(patient_id=patient.id, role="user", content="спал 4 часа"),
                ChatMessage(
                    patient_id=patient.id, role="assistant",
                    content="Про сон лучше отметить в трекере.",
                    request_type="simple", buttons_json=buttons,
                ),
            ])
            await seed.commit()

            factory = async_sessionmaker(seed.bind, expire_on_commit=False)
            app = FastAPI()
            app.include_router(chat_router, prefix="/api/chat")

            async def _sess():
                async with factory() as s:
                    yield s

            app.dependency_overrides[get_async_session] = _sess
            app.dependency_overrides[get_current_user] = lambda: patient

            with TestClient(app) as client:
                resp = client.get(f"/api/chat/history/{patient.id}")

            assert resp.status_code == 200
            body = resp.json()
            assistant = next(m for m in body if m["role"] == "assistant")
            assert assistant["buttons_json"] == buttons
            # у обычного сообщения кнопок нет
            user_msg = next(m for m in body if m["role"] == "user")
            assert user_msg["buttons_json"] is None

    asyncio.run(runner())
