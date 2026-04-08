from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api_errors import register_api_exception_handlers
from app.auth.dependencies import get_current_researcher
from app.llm.memory import st_memory_store
from app.researchers.models import Researcher
from app.researchers.router import router as researcher_router
from app.users.models import User
from core.db.session import get_async_session


@asynccontextmanager
async def researcher_chat_session_ctx() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(Researcher.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def test_researcher_chat_debug_returns_trace_and_uses_st_memory(monkeypatch):
    async def runner():
        st_memory_store.clear_all()
        async with researcher_chat_session_ctx() as seed_session:
            patient = User(full_name="Patient Debug", patient_number=1001)
            researcher = Researcher(username="researcher", password_hash="x", full_name="Researcher Debug")
            seed_session.add(patient)
            seed_session.add(researcher)
            await seed_session.commit()
            await seed_session.refresh(patient)
            await seed_session.refresh(researcher)

            session_factory = async_sessionmaker(seed_session.bind, expire_on_commit=False)
            app = FastAPI()
            register_api_exception_handlers(app)
            app.include_router(researcher_router, prefix="/api/v1")

            async def override_session() -> AsyncSession:
                async with session_factory() as session:
                    yield session

            async def override_researcher() -> Researcher:
                return researcher

            app.dependency_overrides[get_async_session] = override_session
            app.dependency_overrides[get_current_researcher] = override_researcher

            async def fake_daily_context(_patient_id: int, _db: AsyncSession):
                return {"summary": "ctx"}

            calls: list[dict] = []

            async def fake_generate_response(*, patient_id, user_input, router_result, context, db):
                calls.append(
                    {
                        "patient_id": patient_id,
                        "user_input": user_input,
                        "st_memory": list(context.get("st_memory") or []),
                        "model_tier": router_result.model_tier.value,
                    }
                )
                return {
                    "response": f"Ответ на: {user_input}",
                    "tokens_input": 11,
                    "tokens_output": 7,
                    "domain": "sleep",
                    "model": "mock-lite",
                    "pending_st_memory": [
                        {"key": "current_problem", "value": "sleep_problem", "status": "active"},
                        {"key": "current_intent", "value": "practical_day_support", "status": "active"},
                    ],
                    "pending_lt_memory": [],
                    "diagnostics": {
                        "total_latency_ms": 123,
                        "classify": {"request_type": router_result.request_type.value, "effective_domain": "sleep"},
                        "prompt": {"selected_policy": "routine_support", "policy_reasons": ["memory_hint"]},
                        "memory": {
                            "reads": {
                                "st_count": len(context.get("st_memory") or []),
                                "lt_count": 0,
                            },
                            "proposed_st_entries": list(context.get("st_memory") or []),
                            "proposed_lt_entries": [],
                        },
                        "orchestration": {
                            "enabled": True,
                            "mode": "llm_full",
                            "route": {"selected_agents": ["routine"], "primary_agent": "routine"},
                            "specialists": [
                                {
                                    "agent": "routine",
                                    "draft": "Снизь планку на день.",
                                    "recommended_actions": ["одно маленькое дело"],
                                }
                            ],
                        },
                        "llm_call": {"model": "mock-lite", "tokens_input": 11, "tokens_output": 7, "latency_ms": 50},
                    },
                }

            monkeypatch.setattr("app.researchers.router.generate_response", fake_generate_response)
            monkeypatch.setattr("app.llm.morning_service.get_daily_context_for_llm", fake_daily_context)

            client = TestClient(app)

            first = client.post(
                "/api/v1/researcher/chat-debug/message",
                json={
                    "patient_id": patient.id,
                    "message": "Я плохо спал",
                    "forced_model_tier": "pro",
                    "session_id": "dbg-1",
                    "thread_id": "main",
                },
            )
            assert first.status_code == 200
            first_payload = first.json()
            assert first_payload["session_id"] == "dbg-1"
            assert first_payload["thread_id"] == "main"
            assert first_payload["saved_to_chat"] is False
            assert first_payload["memory_before"] == []
            assert len(first_payload["memory_after"]) == 2
            assert first_payload["human_trace"]
            assert any(section["title"] == "Понимание запроса" for section in first_payload["human_trace"])
            assert calls[0]["model_tier"] == "pro"

            second = client.post(
                "/api/v1/researcher/chat-debug/message",
                json={
                    "patient_id": patient.id,
                    "message": "не хочу урок",
                    "session_id": "dbg-1",
                    "thread_id": "main",
                },
            )
            assert second.status_code == 200
            second_payload = second.json()
            assert len(second_payload["memory_before"]) == 2
            assert any(section["title"] == "Память" for section in second_payload["human_trace"])
            assert calls[0]["st_memory"] == []
            assert len(calls[1]["st_memory"]) == 2

        st_memory_store.clear_all()

    asyncio.run(runner())
