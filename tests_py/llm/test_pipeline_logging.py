from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.llm.errors import LLMResponseError
from app.llm.pipeline.pipeline import LLMPipeline
from app.llm.pipeline.types import LLMRequest
from app.llm.router import ModelTier, RequestType, RouterResult
from app.models.llm import LLMRequestLog
from app.users.models import User


@asynccontextmanager
async def pipeline_logging_session_ctx() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.execute(
            text(
                """
                CREATE TABLE llm_request_logs (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    patient_id INTEGER NOT NULL,
                    account_id VARCHAR(20) NOT NULL,
                    model_tier VARCHAR(10) NOT NULL,
                    tokens_input INTEGER NOT NULL DEFAULT 0,
                    tokens_output INTEGER NOT NULL DEFAULT 0,
                    response_time_ms INTEGER NOT NULL DEFAULT 0,
                    request_type VARCHAR(40),
                    success BOOLEAN NOT NULL DEFAULT 1,
                    error_message TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
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
