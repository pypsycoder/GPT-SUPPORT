from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.llm.errors import LLMResponseError
from app.llm.pipeline.pipeline import LLMPipeline
from app.llm.pipeline.types import LLMRequest
from app.llm.router import ModelTier, RequestType, RouterResult
from app.models.llm import LLMRequestLog
from app.users.models import User
from tests_py.sqlite_schema import create_tables


@asynccontextmanager
async def pipeline_logging_session_ctx() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables, User, LLMRequestLog)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_logs_failed_requests_to_db(monkeypatch):
    async def fake_extract_intake_card(state):
        return (
            None,
            {
                "attempts_total": 3,
                "succeeded_on_attempt": None,
                "final_status": "failed_after_retries",
                "failures": [{"attempt": 1, "error_message": "missing required fields"}],
            },
        )

    monkeypatch.setattr("app.llm.langgraph_supervisor.nodes.extract_intake_card", fake_extract_intake_card)

    async with pipeline_logging_session_ctx() as session:
        patient = User(full_name="Patient Logging", patient_number=2001)
        session.add(patient)
        await session.commit()
        await session.refresh(patient)

        with pytest.raises(LLMResponseError):
            await LLMPipeline().process(
                LLMRequest(
                    patient_id=patient.id,
                    user_input="мне тревожно",
                    source="text",
                    router_result=RouterResult(
                        request_type=RequestType.EMOTIONAL,
                        model_tier=ModelTier.PRO,
                        domain_hint="emotion",
                        priority=2,
                    ),
                    db=session,
                )
            )

        result = await session.execute(select(LLMRequestLog))
        log = result.scalar_one()

        assert log.success is False
        assert log.request_type == RequestType.EMOTIONAL.value
        assert log.model_tier == ModelTier.PRO.value
        assert log.error_message == "LLMResponseError: supervisor intake analysis failed after 3 attempts"


@pytest.mark.asyncio
async def test_boundary_guard_account_id_fits_the_column(monkeypatch):
    """Живым прогоном (фаза 2, LLM_test/reports): boundary_guard теговал
    account_id как early_response_source.upper() — "BOUNDARY_GUARD_MEDICAL_URGENT"
    (29 симв.) шире реальной колонки llm_request_logs.account_id VARCHAR(20).
    На Postgres это валило flush() внутри _log_to_database, оставляя сессию
    в pending-rollback — следующий commit() в app/routers/chat.py падал уже
    без обработки, и пациент в кризисе получал 500 вместо ответа. sqlite (эта
    тестовая БД) молча проглатывает превышение длины, поэтому здесь проверяем
    содержимое явно, а не полагаемся на движок, чтобы поймать регресс."""
    monkeypatch.delenv("LLM_ROUTER_L0", raising=False)

    async with pipeline_logging_session_ctx() as session:
        patient = User(full_name="Patient Boundary", patient_number=2002)
        session.add(patient)
        await session.commit()
        await session.refresh(patient)

        response = await LLMPipeline().process(
            LLMRequest(
                patient_id=patient.id,
                user_input="хочу умереть",
                source="text",
                router_result=RouterResult(
                    request_type=RequestType.SAFETY,
                    model_tier=ModelTier.PRO,
                    domain_hint=None,
                    priority=3,
                ),
                db=session,
            )
        )

        assert response.account_id == "BOUNDARY_GUARD_CRISIS"

        result = await session.execute(select(LLMRequestLog))
        log = result.scalar_one()

        assert len(log.account_id) <= 20
        assert log.account_id == "BOUNDARY_GUARD_CRISIS"[:20]
