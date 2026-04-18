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


def test_researcher_chat_debug_returns_graph_v2_trace(monkeypatch):
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

            async def fake_daily_context(_patient_id: int, _db: AsyncSession):
                return {"summary": "ctx"}

            async def fake_generate_response_v2(*, patient_id, user_input, router_result, context, db):
                return {
                    "response": "Сочувствую. От чего тебе тревожно?",
                    "tokens_input": 11,
                    "tokens_output": 7,
                    "domain": "emotion",
                    "model": "mock-lite",
                    "requested_model_tier": router_result.model_tier.value,
                    "actual_model_tier": router_result.model_tier.value,
                    "account_id": "SUPERVISOR",
                    "pending_st_memory": [],
                    "pending_lt_memory": [],
                    "supervisor_state": {
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
                    },
                    "supervisor_state_delta": {
                        "goal": "тревога",
                        "pending_question": {
                            "slot_name": "clarify",
                            "question_text": "От чего тебе тревожно?",
                            "expected_kind": "free_text",
                            "attempts": 1,
                            "reason": "intake",
                        },
                        "needs_clarification": True,
                    },
                    "diagnostics": {
                        "total_latency_ms": 123,
                        "classify": {
                            "request_type": router_result.request_type.value,
                            "effective_domain": "emotion",
                            "supervisor_state_seeded": bool(context.get("supervisor_state")),
                        },
                        "supervisor": {
                            "enabled": True,
                            "message_type": "full_message",
                            "graph_path": ["intake_analyze", "intake_validate", "intake_execute"],
                            "selected_agents": [],
                            "needs_clarification": True,
                            "intake": {
                                "card": {
                                    "problem": "тревога",
                                    "context": "причина пока не названа",
                                    "needs_clarification": "да",
                                    "question": "От чего тебе тревожно?",
                                    "ready_to_delegate": "нет",
                                    "rationale": "Нужен один уточняющий вопрос.",
                                },
                                "llm": {
                                    "attempts_total": 1,
                                    "succeeded_on_attempt": 1,
                                    "final_status": "success",
                                },
                            },
                            "delegation": {},
                            "expert": {},
                            "state_after": {
                                "goal": "тревога",
                                "needs_clarification": True,
                            },
                        },
                        "memory": {
                            "reads": {
                                "st_count": len(context.get("st_memory") or []),
                                "lt_count": 0,
                            },
                            "proposed_st_entries": [],
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
                    "forced_model_tier": "pro",
                    "session_id": "dbg-1",
                    "thread_id": "main",
                },
            )

            assert response.status_code == 200
            payload = response.json()
            supervisor_section = next(section for section in payload["human_trace"] if section["title"] == "Supervisor")
            assert any("Graph path: intake_analyze -> intake_validate -> intake_execute." == item for item in supervisor_section["items"])
            assert payload["supervisor_state"]["pending_question"]["question_text"] == "От чего тебе тревожно?"

        st_memory_store.clear_all()

    asyncio.run(runner())


def test_researcher_chat_debug_can_save_graph_v2_report(monkeypatch, tmp_path: Path):
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
                        "selected_turns": [1],
                        "turns": [
                            {
                                "turn_number": 1,
                                "user_message": "мне тревожно",
                                "assistant_reply": "Сочувствую. От чего тебе тревожно?",
                                "human_trace": [{"title": "Supervisor", "items": ["Graph path: intake_analyze -> intake_validate -> intake_execute."]}],
                                "diagnostics_json": {
                                    "supervisor": {
                                        "graph_path": ["intake_analyze", "intake_validate", "intake_execute"],
                                        "intake": {
                                            "card": {
                                                "problem": "тревога",
                                                "context": "причина пока не названа",
                                                "needs_clarification": "да",
                                                "question": "От чего тебе тревожно?",
                                                "ready_to_delegate": "нет",
                                                "rationale": "Нужен один уточняющий вопрос.",
                                            }
                                        },
                                        "delegation": {},
                                        "expert": {},
                                    }
                                },
                                "state_before": {},
                                "state_after": {"needs_clarification": True},
                            }
                        ],
                    }
                },
            )

            assert response.status_code == 200
            payload = response.json()
            saved_path = tmp_path / payload["relative_path"]
            contents = saved_path.read_text(encoding="utf-8")
            assert "# Ход 1" in contents
            assert "## Graph" in contents
            assert "Intake:" in contents
            assert "Path: intake_analyze -> intake_validate -> intake_execute" in contents

    asyncio.run(runner())


def test_researcher_chat_debug_returns_json_error_for_graph_v2_failure(monkeypatch):
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
                    "supervisor intake analysis failed after 3 attempts",
                    diagnostics={
                        "supervisor": {
                            "enabled": True,
                            "intake": {
                                "llm": {
                                    "attempts_total": 3,
                                    "succeeded_on_attempt": None,
                                    "final_status": "failed_after_retries",
                                    "failures": [
                                        {
                                            "attempt": 1,
                                            "error_type": "ValueError",
                                            "error_message": "missing required fields",
                                            "raw_excerpt": "Internal Server Error",
                                        }
                                    ],
                                }
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
            assert payload["detail"] == "supervisor intake analysis failed after 3 attempts"
            assert payload["diagnostics_json"]["supervisor"]["intake"]["llm"]["final_status"] == "failed_after_retries"
            assert payload["diagnostics_json"]["supervisor"]["intake"]["llm"]["failures"][0]["raw_excerpt"] == "Internal Server Error"

    asyncio.run(runner())
