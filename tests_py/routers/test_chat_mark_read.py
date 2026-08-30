from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.dependencies import get_current_user
from app.models.llm import ChatMessage, ChatSupervisorState
from app.routers.chat import router as chat_router
from app.users.models import User
from core.db.session import get_async_session
from tests_py.sqlite_schema import create_tables


@asynccontextmanager
async def chat_session_ctx() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables, User, ChatMessage, ChatSupervisorState)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def test_mark_read_clears_only_current_patient_assistant_messages():
    async def runner():
        async with chat_session_ctx() as seed_session:
            patient = User(full_name="Patient MarkRead", patient_number=3001)
            other = User(full_name="Other Patient", patient_number=3002)
            seed_session.add_all([patient, other])
            await seed_session.commit()
            await seed_session.refresh(patient)
            await seed_session.refresh(other)

            seed_session.add_all(
                [
                    # непрочитанный проактив нашего пациента — должен закрыться
                    ChatMessage(
                        patient_id=patient.id,
                        role="assistant",
                        content="утренний дайджест",
                        request_type="morning",
                        is_read=False,
                    ),
                    ChatMessage(
                        patient_id=patient.id,
                        role="assistant",
                        content="напоминание",
                        request_type="motivator",
                        is_read=False,
                    ),
                    # сообщение пациента — роль user, не трогаем
                    ChatMessage(
                        patient_id=patient.id,
                        role="user",
                        content="привет",
                        is_read=False,
                    ),
                    # чужой непрочитанный проактив — не трогаем
                    ChatMessage(
                        patient_id=other.id,
                        role="assistant",
                        content="чужой дайджест",
                        request_type="morning",
                        is_read=False,
                    ),
                ]
            )
            await seed_session.commit()

            session_factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = FastAPI()
            app.include_router(chat_router, prefix="/api/chat")

            async def override_session() -> AsyncSession:
                async with session_factory() as session:
                    yield session

            async def override_user() -> User:
                return patient

            app.dependency_overrides[get_async_session] = override_session
            app.dependency_overrides[get_current_user] = override_user

            with TestClient(app) as client:
                first = client.post("/api/chat/mark-read")
                second = client.post("/api/chat/mark-read")

            assert first.status_code == 200
            assert first.json() == {"updated": 2}
            # идемпотентность: второй вызов ничего не меняет
            assert second.status_code == 200
            assert second.json() == {"updated": 0}

            async with session_factory() as check_session:
                rows = (
                    await check_session.execute(
                        select(ChatMessage).order_by(ChatMessage.id)
                    )
                ).scalars().all()
                by_content = {r.content: r for r in rows}

            assert by_content["утренний дайджест"].is_read is True
            assert by_content["напоминание"].is_read is True
            # роль user не затронута
            assert by_content["привет"].is_read is False
            # чужой пациент не затронут
            assert by_content["чужой дайджест"].is_read is False

    asyncio.run(runner())
