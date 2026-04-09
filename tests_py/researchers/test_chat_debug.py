from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api_errors import register_api_exception_handlers
from app.auth.dependencies import get_current_researcher
from app.llm.errors import LLMResponseError
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


def test_researcher_chat_debug_returns_rich_supervisor_trace(monkeypatch):
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

            async def fake_generate_response_v2(*, patient_id, user_input, router_result, context, db):
                calls.append(
                    {
                        "patient_id": patient_id,
                        "user_input": user_input,
                        "st_memory": list(context.get("st_memory") or []),
                        "model_tier": router_result.model_tier.value,
                        "supervisor_state": dict(context.get("supervisor_state") or {}),
                    }
                )
                return {
                    "response": f"Ответ на: {user_input}",
                    "tokens_input": 11,
                    "tokens_output": 7,
                    "domain": "sleep",
                    "model": "mock-lite",
                    "requested_model_tier": router_result.model_tier.value,
                    "actual_model_tier": router_result.model_tier.value,
                    "account_id": "SUPERVISOR",
                    "pending_st_memory": [
                        {"key": "current_problem", "value": "sleep_problem", "status": "active"},
                        {"key": "current_intent", "value": "practical_day_support", "status": "active"},
                    ],
                    "pending_lt_memory": [],
                    "supervisor_state": {
                        "domain": "health",
                        "intent": "plan",
                        "goal": "sleep_problem",
                        "slots": {"distress_level": 7},
                        "risk_flags": ["distress"],
                        "signals": ["sleep"],
                        "facts": ["bad_sleep"],
                        "pending_question": None,
                        "last_selected_agents": ["planning"],
                        "needs_clarification": False,
                    },
                    "supervisor_state_delta": {
                        "domain": "health",
                        "intent": "plan",
                        "goal": "sleep_problem",
                        "risk_flags_add": ["distress"],
                        "last_selected_agents_set": ["planning"],
                    },
                    "diagnostics": {
                        "total_latency_ms": 123,
                        "classify": {
                            "request_type": router_result.request_type.value,
                            "effective_domain": "sleep",
                            "supervisor_state_seeded": bool(context.get("supervisor_state")),
                        },
                        "supervisor": {
                            "enabled": True,
                            "message_type": "full_message",
                            "selected_agents": ["planning"],
                            "used_pending_answer": False,
                            "needs_clarification": False,
                            "state_delta": {
                                "domain": "health",
                                "intent": "plan",
                                "goal": "sleep_problem",
                                "risk_flags_add": ["distress"],
                            },
                            "state_after": {
                                "domain": "health",
                                "intent": "plan",
                                "goal": "sleep_problem",
                                "slots": {"distress_level": 7},
                                "risk_flags": ["distress"],
                                "signals": ["sleep"],
                                "facts": ["bad_sleep"],
                                "pending_question": None,
                                "last_selected_agents": ["planning"],
                                "needs_clarification": False,
                            },
                            "turn_diagnostics": {
                                "classification": {
                                    "domain": "health",
                                    "intent": "plan",
                                    "goal": "sleep_problem",
                                    "signals": ["sleep"],
                                    "risk_flags": ["distress"],
                                    "facts": ["bad_sleep"],
                                }
                            },
                        },
                        "memory": {
                            "reads": {
                                "st_count": len(context.get("st_memory") or []),
                                "lt_count": 0,
                            },
                            "proposed_st_entries": list(context.get("st_memory") or []),
                            "proposed_lt_entries": [],
                        },
                        "orchestration": {
                            "skipped": True,
                            "reason": "supervisor_turn",
                        },
                        "validation": {
                            "triggered": True,
                            "status": "supervisor_draft_kept",
                        },
                        "stages": [
                            {"name": "boundary_guard", "status": "ok", "latency_ms": 1},
                            {"name": "classification", "status": "ok", "latency_ms": 2},
                            {"name": "supervisor", "status": "ok", "latency_ms": 3},
                            {"name": "context", "status": "ok", "latency_ms": 0},
                            {"name": "intake", "status": "ok", "latency_ms": 0},
                            {"name": "orchestration", "status": "ok", "latency_ms": 0},
                            {"name": "validation", "status": "ok", "latency_ms": 1},
                            {"name": "memory_write", "status": "ok", "latency_ms": 1},
                        ],
                        "patient_context": {"skipped": True, "reason": "supervisor_turn"},
                        "intake": {"skipped": True, "reason": "supervisor_turn"},
                    },
                }

            monkeypatch.setattr("app.researchers.router.generate_response_v2", fake_generate_response_v2)
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
            assert first_payload["supervisor_state"]["goal"] == "sleep_problem"
            assert first_payload["supervisor_state_delta"]["goal"] == "sleep_problem"
            assert first_payload["human_trace"]
            assert all(section["title"] != "Понимание запроса" for section in first_payload["human_trace"])
            supervisor_section = next(
                section for section in first_payload["human_trace"] if section["title"] == "Supervisor"
            )
            assert any("Supervisor определил тип хода: full_message." == item for item in supervisor_section["items"])
            assert any("Подключенные expert-агенты: planning." == item for item in supervisor_section["items"])
            assert calls[0]["model_tier"] == "pro"
            assert calls[0]["supervisor_state"] == {}

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
            assert calls[1]["supervisor_state"]["goal"] == "sleep_problem"

        st_memory_store.clear_all()

    asyncio.run(runner())


def test_researcher_chat_debug_can_save_report_to_project(monkeypatch, tmp_path: Path):
    async def runner():
        async with researcher_chat_session_ctx() as seed_session:
            patient = User(full_name="Patient Debug", patient_number=1002)
            researcher = Researcher(username="researcher2", password_hash="x", full_name="Researcher Debug")
            seed_session.add(patient)
            seed_session.add(researcher)
            await seed_session.commit()
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

            reports_dir = tmp_path / "LLM_test" / "reports"
            monkeypatch.setattr("app.researchers.router._DEBUG_REPORTS_DIR", reports_dir)
            monkeypatch.setattr("app.researchers.router._PROJECT_ROOT", tmp_path)

            client = TestClient(app)
            response = client.post(
                "/api/v1/researcher/chat-debug/save-report",
                json={
                    "report_data": {
                        "session_id": "dbg-save",
                        "selected_turns": [1, 2],
                        "turns": [{"turn_number": 1}, {"turn_number": 2}],
                    }
                },
            )

            assert response.status_code == 200
            payload = response.json()
            assert payload["ok"] is True
            assert payload["relative_path"].startswith("LLM_test/reports/")
            saved_path = tmp_path / payload["relative_path"]
            assert saved_path.exists()
            contents = saved_path.read_text(encoding="utf-8")
            assert '"session_id": "dbg-save"' in contents
            assert '"selected_turns": [' in contents

    asyncio.run(runner())


def test_researcher_chat_debug_returns_json_error_for_llm_runtime_failure(monkeypatch):
    async def runner():
        async with researcher_chat_session_ctx() as seed_session:
            patient = User(full_name="Patient Debug", patient_number=1003)
            researcher = Researcher(username="researcher3", password_hash="x", full_name="Researcher Debug")
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

            async def fake_daily_context(_patient_id: int, _db: AsyncSession):
                return {"summary": "ctx"}

            async def fake_generate_response_v2(*, patient_id, user_input, router_result, context, db):
                raise LLMResponseError(
                    "supervisor goal analysis failed after 3 attempts",
                    diagnostics={
                        "supervisor": {
                            "enabled": True,
                            "goal_analysis": {
                                "used": True,
                                "attempts_total": 3,
                                "succeeded_on_attempt": None,
                                "final_status": "failed_after_retries",
                                "failures": [
                                    {
                                        "attempt": 1,
                                        "error_type": "ValueError",
                                        "error_message": "goal analysis returned non-json payload",
                                        "raw_excerpt": "Internal Server Error",
                                    }
                                ],
                            },
                        }
                    },
                )

            app.dependency_overrides[get_async_session] = override_session
            app.dependency_overrides[get_current_researcher] = override_researcher
            monkeypatch.setattr("app.researchers.router.generate_response_v2", fake_generate_response_v2)
            monkeypatch.setattr("app.llm.morning_service.get_daily_context_for_llm", fake_daily_context)

            client = TestClient(app)
            response = client.post(
                "/api/v1/researcher/chat-debug/message",
                json={
                    "patient_id": patient.id,
                    "message": "мне тревожно",
                    "session_id": "dbg-err",
                    "thread_id": "main",
                },
            )

            assert response.status_code == 502
            payload = response.json()
            assert payload["detail"] == "supervisor goal analysis failed after 3 attempts"
            assert payload["response"] == "Ошибка debug-чата: supervisor goal analysis failed after 3 attempts"
            assert payload["diagnostics_json"]["supervisor"]["goal_analysis"]["final_status"] == "failed_after_retries"
            assert payload["diagnostics_json"]["supervisor"]["goal_analysis"]["failures"][0]["raw_excerpt"] == "Internal Server Error"
            assert payload["human_trace"]
            assert payload["supervisor_state"] is None

    asyncio.run(runner())
