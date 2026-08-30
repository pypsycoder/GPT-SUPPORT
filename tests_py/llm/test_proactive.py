"""Проактив: сборка очереди, приоритет, дедуп, is_read."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.llm import proactive
from app.llm.anomaly import AnomalyAlert
from app.llm.router import ModelTier, RequestType
from app.models.llm import ChatMessage
from tests_py.sqlite_schema import create_tables


# --------------------------------------------------------------------------- #
# generate_daily_queue — приоритет и потолок
# --------------------------------------------------------------------------- #

def _alert(sev: str, typ: str = "systolic_bp", value: float = 190, domain: str = "vitals") -> AnomalyAlert:
    return AnomalyAlert(type=typ, value=value, threshold=180, severity=sev, domain_hint=domain)


def _patch_signals(monkeypatch, *, anomalies=None, scores=None, priority=None, has_data=True):
    async def _fake_anomalies(patient_id, db):
        return list(anomalies or [])

    async def _fake_scores(patient_id, db):
        return dict(scores or {})

    def _fake_priority(s):
        return list(priority or [])

    async def _fake_has_data(patient_id, db):
        return has_data

    monkeypatch.setattr(proactive, "check_anomalies", _fake_anomalies)
    monkeypatch.setattr("app.llm.domain_scorer.calculate_domain_scores", _fake_scores)
    monkeypatch.setattr("app.llm.domain_scorer.get_priority_domains", _fake_priority)
    monkeypatch.setattr("app.llm.domain_scorer.has_tracked_data", _fake_has_data)


def test_queue_orders_critical_then_warning_then_domains(monkeypatch):
    _patch_signals(
        monkeypatch,
        anomalies=[_alert("WARNING", domain="vitals"), _alert("CRITICAL", domain="vitals")],
        scores={"sleep": 0.2},
        priority=["sleep"],
    )

    queue = asyncio.run(proactive.generate_daily_queue(1, db=object()))

    assert [m.router_result.request_type for m in queue][:2] == [RequestType.SAFETY, RequestType.PROACTIVE]
    assert queue[0].router_result.model_tier == ModelTier.PRO      # CRITICAL
    assert queue[-1].domain_hint == "sleep"                        # плохой домен — в хвосте


def test_queue_caps_at_three(monkeypatch):
    _patch_signals(
        monkeypatch,
        anomalies=[_alert("WARNING", domain=d) for d in ("a", "b", "c", "d")],
        scores={"sleep": 0.1},
        priority=["sleep"],
    )

    queue = asyncio.run(proactive.generate_daily_queue(1, db=object()))

    assert len(queue) == 3


def test_queue_skips_domain_already_covered_by_anomaly(monkeypatch):
    _patch_signals(
        monkeypatch,
        anomalies=[_alert("WARNING", domain="vitals")],
        scores={"vitals": 0.1, "sleep": 0.2},
        priority=["vitals", "sleep"],
    )

    queue = asyncio.run(proactive.generate_daily_queue(1, db=object()))
    domains = [m.domain_hint for m in queue]

    assert domains.count("vitals") == 1        # не задублирован доменным сообщением
    assert "sleep" in domains


def test_queue_ignores_domains_scored_at_or_above_half(monkeypatch):
    _patch_signals(monkeypatch, anomalies=[], scores={"sleep": 0.5}, priority=["sleep"])

    queue = asyncio.run(proactive.generate_daily_queue(1, db=object()))

    assert queue == []


def test_queue_cold_start_skips_domain_messages(monkeypatch):
    # плохой score есть, но данных у пациента нет — доменное сообщение «из ничего»
    _patch_signals(
        monkeypatch, anomalies=[], scores={"sleep": 0.1}, priority=["sleep"], has_data=False,
    )

    queue = asyncio.run(proactive.generate_daily_queue(1, db=object()))

    assert queue == []


def test_queue_cold_start_still_allows_critical_anomaly(monkeypatch):
    _patch_signals(
        monkeypatch, anomalies=[_alert("CRITICAL")], scores={}, priority=[], has_data=False,
    )

    queue = asyncio.run(proactive.generate_daily_queue(1, db=object()))

    assert [m.router_result.request_type for m in queue] == [RequestType.SAFETY]


def test_critical_anomaly_is_safety_pro_warning_is_proactive_lite():
    crit = proactive._make_anomaly_message(1, _alert("CRITICAL"))
    warn = proactive._make_anomaly_message(1, _alert("WARNING"))

    assert crit.router_result.request_type == RequestType.SAFETY
    assert crit.router_result.model_tier == ModelTier.PRO
    assert warn.router_result.request_type == RequestType.PROACTIVE
    assert warn.router_result.model_tier == ModelTier.LITE


# --------------------------------------------------------------------------- #
# deliver_proactive_messages — дедуп 6ч и is_read
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def _sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        execution_options={"schema_translate_map": {"users": None, "llm": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(create_tables, ChatMessage)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


class _FakePipeline:
    def __init__(self):
        self.calls = 0

    async def process(self, request):
        self.calls += 1
        return type(
            "R", (), {"response": "тёплый вопрос", "tokens_input": 1, "tokens_output": 1,
                      "model": "GigaChat-2", "domain": "sleep"},
        )()


def test_deliver_skips_when_recent_proactive_exists(monkeypatch):
    async def runner():
        async with _sqlite_session() as db:
            db.add(ChatMessage(
                patient_id=1, role="assistant", content="было час назад",
                request_type="proactive", created_at=datetime.utcnow() - timedelta(hours=1),
            ))
            await db.commit()

            fake = _FakePipeline()
            monkeypatch.setattr(proactive, "_llm_pipeline", fake)

            async def _queue(pid, session):
                raise AssertionError("очередь не должна строиться при активном дедупе")

            monkeypatch.setattr(proactive, "generate_daily_queue", _queue)

            await proactive.deliver_proactive_messages(1, db)

            assert fake.calls == 0

    asyncio.run(runner())


def test_deliver_writes_unread_assistant_message(monkeypatch):
    async def runner():
        async with _sqlite_session() as db:
            fake = _FakePipeline()
            monkeypatch.setattr(proactive, "_llm_pipeline", fake)

            msg = proactive._make_domain_message(1, "sleep", 0.2)

            async def _queue(pid, session):
                return [msg]

            monkeypatch.setattr(proactive, "generate_daily_queue", _queue)

            await proactive.deliver_proactive_messages(1, db)

            rows = (await db.execute(select(ChatMessage))).scalars().all()
            assert len(rows) == 1
            assert rows[0].request_type == "proactive"
            assert rows[0].is_read is False

    asyncio.run(runner())
