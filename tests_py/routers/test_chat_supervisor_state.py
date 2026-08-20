from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.dependencies import get_current_user
from app.llm.pipeline import LLMResponse
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


def test_patient_chat_persists_supervisor_state_between_messages(monkeypatch):
    async def runner():
        async with chat_session_ctx() as seed_session:
            patient = User(full_name="Patient State", patient_number=2001)
            seed_session.add(patient)
            await seed_session.commit()
            await seed_session.refresh(patient)

            session_factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = FastAPI()
            app.include_router(chat_router, prefix="/api/chat")

            async def override_session() -> AsyncSession:
                async with session_factory() as session:
                    yield session

            async def override_user() -> User:
                return patient

            class FakePipeline:
                def __init__(self):
                    self.requests = []

                async def process(self, request):
                    self.requests.append(request)
                    turn = len(self.requests)
                    if turn == 1:
                        supervisor_state = {
                            "goal": "тревога",
                            "slots": {"intake_context": "причина пока не названа"},
                            "risk_flags": [],
                            "signals": [],
                            "facts": [],
                            "pending_question": {
                                "slot_name": "clarify",
                                "question_text": "От чего тебе тревожно?",
                                "expected_kind": "free_text",
                                "attempts": 1,
                                "reason": "intake",
                            },
                            "last_selected_agents": [],
                            "needs_clarification": True,
                            "clarification_streak": 1,
                        }
                    else:
                        supervisor_state = {
                            **dict(request.supervisor_state or {}),
                            "pending_question": None,
                            "needs_clarification": False,
                            "clarification_streak": 0,
                        }

                    return LLMResponse(
                        response="ok",
                        tokens_input=1,
                        tokens_output=1,
                        model="mock-lite",
                        domain="emotion",
                        response_time_ms=10,
                        account_id="SUPERVISOR",
                        requested_model_tier=request.router_result.model_tier.value,
                        actual_model_tier=request.router_result.model_tier.value,
                        supervisor_state=supervisor_state,
                    )

            fake_pipeline = FakePipeline()
            monkeypatch.setattr("app.routers.chat._llm_pipeline", fake_pipeline)

            app.dependency_overrides[get_async_session] = override_session
            app.dependency_overrides[get_current_user] = override_user

            with TestClient(app) as client:
                first = client.post(
                    "/api/chat/message",
                    json={"patient_id": patient.id, "message": "мне тревожно", "source": "text"},
                )
                second = client.post(
                    "/api/chat/message",
                    json={"patient_id": patient.id, "message": "из-за диализа", "source": "text"},
                )

            assert first.status_code == 200
            assert second.status_code == 200
            assert fake_pipeline.requests[0].supervisor_state is None
            assert fake_pipeline.requests[1].supervisor_state["pending_question"]["question_text"] == (
                "От чего тебе тревожно?"
            )

            async with session_factory() as check_session:
                result = await check_session.execute(
                    select(ChatSupervisorState).where(
                        ChatSupervisorState.patient_id == patient.id,
                        ChatSupervisorState.thread_id == "default",
                    )
                )
                state_row = result.scalar_one()
                assert state_row.thread_id == "default"
                assert state_row.state_json["pending_question"] is None
                assert state_row.state_json["needs_clarification"] is False

    asyncio.run(runner())
