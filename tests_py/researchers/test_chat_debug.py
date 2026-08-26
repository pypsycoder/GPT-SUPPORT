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
from app.llm.pipeline import LLMResponse
from app.llm.router import ModelTier, RequestType, RouterResult
from app.models.llm import ChatMessage, ChatSupervisorState, PatientFact
from app.researchers.models import Researcher
from app.researchers.router import router as researcher_router
from app.users.models import User
from core.db.session import get_async_session
from tests_py.sqlite_schema import create_tables


@asynccontextmanager
async def researcher_chat_session_ctx() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            create_tables, User, Researcher, ChatMessage, ChatSupervisorState, PatientFact
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def test_researcher_chat_debug_returns_agent_trace(monkeypatch):
    async def runner():
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

            class FakePipeline:
                async def process(self, request):
                    return LLMResponse(
                        response="Сочувствую. От чего тебе тревожно?",
                        tokens_input=11,
                        tokens_output=7,
                        domain="emotion",
                        model="mock-lite",
                        response_time_ms=123,
                        requested_model_tier=request.router_result.model_tier.value,
                        actual_model_tier=request.router_result.model_tier.value,
                        account_id="SUPERVISOR",
                        pending_st_memory=[],
                        pending_lt_memory=[],
                        supervisor_state={
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
                        supervisor_state_delta={
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
                        diagnostics={
                            "total_latency_ms": 123,
                            "classify": {
                                "request_type": request.router_result.request_type.value,
                                "effective_domain": "emotion",
                                "supervisor_state_seeded": bool(request.supervisor_state),
                            },
                            "supervisor": {
                                "enabled": True,
                                "message_type": "full_message",
                                "graph_path": ["agent"],
                                "selected_agents": [],
                                "needs_clarification": True,
                                "agent": {
                                    "intent": "emotional_support",
                                    "safety_level": "none",
                                    "safety_kind": "none",
                                    "next_action": "уточнить причину тревоги",
                                },
                                "state_after": {
                                    "goal": "тревога",
                                    "needs_clarification": True,
                                },
                            },
                            "memory": {
                                "reads": {"st_count": 0, "lt_count": 0},
                                "proposed_st_entries": [],
                                "proposed_lt_entries": [],
                            },
                            "response": {
                                "source": "supervisor",
                                "account_id": "SUPERVISOR",
                            },
                            "stages": [
                                {"name": "boundary_guard", "status": "ok", "latency_ms": 1},
                                {"name": "classification", "status": "ok", "latency_ms": 2},
                                {"name": "supervisor", "status": "ok", "latency_ms": 3},
                                {"name": "memory_write", "status": "ok", "latency_ms": 1},
                            ],
                        },
                    )

            app.dependency_overrides[get_async_session] = override_session
            app.dependency_overrides[get_current_researcher] = override_researcher
            monkeypatch.setattr("app.researchers.router._llm_pipeline", FakePipeline())

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
            assert any("Graph path: agent." == item for item in supervisor_section["items"])
            assert payload["supervisor_state"]["pending_question"]["question_text"] == "От чего тебе тревожно?"

    asyncio.run(runner())


def test_researcher_chat_debug_can_save_agent_report(monkeypatch, tmp_path: Path):
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
                                "human_trace": [{"title": "Supervisor", "items": ["Graph path: agent."]}],
                                "diagnostics_json": {
                                    "supervisor": {
                                        "graph_path": ["agent"],
                                        "agent": {
                                            "intent": "emotional_support",
                                            "safety_level": "none",
                                            "next_action": "уточнить причину тревоги",
                                        },
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
            assert "Agent:" in contents
            assert "Path: agent" in contents

    asyncio.run(runner())


def test_researcher_chat_debug_keeps_router_tier_when_not_forced(monkeypatch):
    async def runner():
        async with researcher_chat_session_ctx() as seed_session:
            patient = User(full_name="Patient Debug", patient_number=1004)
            researcher = Researcher(username="researcher4", password_hash="x", full_name="Researcher Debug")
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

            class FakePipeline:
                async def process(self, request):
                    assert request.router_result is not None
                    assert request.router_result.model_tier == ModelTier.PRO
                    assert request.strict_model_tier is False
                    return LLMResponse(
                        response="Ответ без принудительного tier.",
                        tokens_input=3,
                        tokens_output=4,
                        domain="emotion",
                        model="mock-pro",
                        response_time_ms=20,
                        requested_model_tier=request.router_result.model_tier.value,
                        actual_model_tier=request.router_result.model_tier.value,
                        account_id="SUPERVISOR",
                        pending_st_memory=[],
                        pending_lt_memory=[],
                        supervisor_state=None,
                        supervisor_state_delta={},
                        diagnostics={},
                    )

            app.dependency_overrides[get_async_session] = override_session
            app.dependency_overrides[get_current_researcher] = override_researcher
            monkeypatch.setattr("app.researchers.router._llm_pipeline", FakePipeline())
            async def _fake_classify_request_async(_message, _source):
                return RouterResult(
                    request_type=RequestType.EMOTIONAL,
                    model_tier=ModelTier.PRO,
                    domain_hint="emotion",
                    priority=2,
                )

            monkeypatch.setattr(
                "app.researchers.router.classify_request_async",
                _fake_classify_request_async,
            )

            client = TestClient(app)
            response = client.post(
                "/api/v1/researcher/chat-debug/message",
                json={
                    "patient_id": patient.id,
                    "message": "мне тревожно",
                    "session_id": "dbg-no-force",
                    "thread_id": "main",
                },
            )

            assert response.status_code == 200
            payload = response.json()
            assert payload["requested_model_tier"] == ModelTier.PRO.value
            assert payload["actual_model_tier"] == ModelTier.PRO.value

    asyncio.run(runner())


def test_researcher_chat_debug_returns_json_error_for_agent_failure(monkeypatch):
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

            class FakePipeline:
                async def process(self, request):
                    raise LLMResponseError(
                        "agent card failed schema validation twice",
                        diagnostics={
                            "supervisor": {
                                "enabled": True,
                                "graph_path": ["agent"],
                                "error": "schema validation failed twice: missing required fields",
                            }
                        },
                    )

            app.dependency_overrides[get_async_session] = override_session
            app.dependency_overrides[get_current_researcher] = override_researcher
            monkeypatch.setattr("app.researchers.router._llm_pipeline", FakePipeline())

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
            assert payload["detail"] == "agent card failed schema validation twice"
            assert payload["diagnostics_json"]["supervisor"]["error"] == "schema validation failed twice: missing required fields"

    asyncio.run(runner())
