from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.llm import agent
from app.llm.agent.schemas import AgentReply
from app.llm.pipeline.pipeline import LLMPipeline
from app.llm.pipeline.types import LLMRequest
from app.llm.pool import FunctionCallResult, StructuredResult
from app.llm.router import ModelTier, RequestType, RouterResult
from app.llm.safety_classifier import SafetyAssessment
from app.models.llm import (
    ChatMessage,
    ChatSummary,
    ChatSupervisorState,
    LLMRequestLog,
    PatientFact,
)
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
        await conn.run_sync(
            create_tables,
            User,
            LLMRequestLog,
            PatientFact,
            ChatMessage,
            ChatSummary,
            ChatSupervisorState,
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_boundary_guard_account_id_fits_the_column():
    """Живым прогоном (фаза 2, LLM_test/reports): boundary_guard теговал
    account_id как early_response_source.upper() — "BOUNDARY_GUARD_MEDICAL_URGENT"
    (29 симв.) шире прежней колонки llm_request_logs.account_id VARCHAR(20).
    На Postgres это валило flush() внутри _log_to_database, оставляя сессию
    в pending-rollback — следующий commit() в app/routers/chat.py падал уже
    без обработки, и пациент в кризисе получал 500 вместо ответа.

    Ревизия 20260901_01 расширила колонку до VARCHAR(64), а pipeline.py убрал
    срез [:20] — тег источника раннего ответа теперь пишется целиком. Проверяем
    это явно: sqlite (тестовая БД) молча проглотил бы и обрезку, и превышение."""
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

        assert log.account_id == "BOUNDARY_GUARD_CRISIS"  # целиком, без среза [:20]
        # самый длинный тег источника раннего ответа помещается в колонку
        assert len("BOUNDARY_GUARD_MEDICAL_URGENT") <= LLMRequestLog.__table__.c.account_id.type.length


# ---------------------------------------------------------------------------
# Фаза 5 Track B: response_source / technique_id / safety_level / diagnostics_json
# (docs/agent/PHASE5_RESEARCH_INSTRUMENTATION_SPEC.md)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crisis_turn_logs_diagnostics_and_urgent_safety_level():
    """L0-кризис — самый частый путь и единственный, где diagnostics['boundary_guard']
    не содержит ключа "level" (он есть только в ветке LLM-классификатора).
    safety_level должен браться из context.l0.safety_level, а не оттуда — иначе
    ровно кризисные ходы остаются без safety_level в логе."""
    async with pipeline_logging_session_ctx() as session:
        patient = User(full_name="Patient Crisis Log", patient_number=2003)
        session.add(patient)
        await session.commit()
        await session.refresh(patient)

        await LLMPipeline().process(
            LLMRequest(
                patient_id=patient.id,
                user_input="не хочу больше жить",
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

        log = (await session.execute(select(LLMRequestLog))).scalar_one()

        assert log.response_source == "boundary_guard_crisis"
        assert log.safety_level == "urgent"
        assert log.technique_id is None
        assert log.diagnostics_json is not None
        assert log.diagnostics_json["boundary_guard"]["type"] == "crisis_signal"
        assert "level" not in log.diagnostics_json["boundary_guard"]


def _card(**overrides) -> AgentReply:
    payload = {
        "reply": "Понимаю, это непросто. Давай разберёмся вместе.",
        "intent": "emotional_support",
        "technique_id": "p101",
        "safety_level": "none",
        "safety_kind": "none",
        "safety_reason": "нет",
        "next_action": "нет",
        "memory_candidates": [],
    }
    payload.update(overrides)
    return AgentReply.model_validate(payload)


class _StubClient:
    account_id = "A1-pro"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    async def call_with_functions(self, messages, system_prompt, **kwargs):
        return FunctionCallResult(
            content="", function_call=None, functions_state_id=None, finish_reason="stop"
        )

    async def structured(self, messages, system_prompt, schema, **kwargs):
        return self.outcomes.pop(0)


@pytest.mark.asyncio
async def test_full_agent_turn_logs_technique_id_and_none_safety_level(monkeypatch):
    client = _StubClient([
        StructuredResult(parsed=_card(), raw_text="{}", tokens_in=700, tokens_out=90, latency_ms=800)
    ])

    async def _fake_get_available(model_tier, *, allow_fallback=False, sticky_key=None):
        return client

    monkeypatch.setattr(agent.loop.pool, "get_available", _fake_get_available)

    async def _fake_safety(text, context=None):
        return SafetyAssessment(level="none", subject="self", available=True)

    monkeypatch.setattr("app.llm.pipeline.stages.boundary_guard.safety_classifier.classify", _fake_safety)

    async with pipeline_logging_session_ctx() as session:
        patient = User(full_name="Patient Technique Log", patient_number=2004)
        session.add(patient)
        await session.commit()
        await session.refresh(patient)

        await LLMPipeline().process(
            LLMRequest(
                patient_id=patient.id,
                user_input="последние дни всё валится из рук, ничего не радует",
                source="text",
                router_result=RouterResult(RequestType.EMOTIONAL, ModelTier.PRO, "emotion", 2),
                db=session,
            )
        )

        log = (await session.execute(select(LLMRequestLog))).scalar_one()

        assert log.response_source == "supervisor"
        assert log.technique_id == "p101"
        assert log.safety_level == "none"
        assert log.diagnostics_json["supervisor"]["agent"]["technique_id"] == "p101"
