from __future__ import annotations

import pytest

import core.db.engine as db_engine
from app.llm import on_login


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


class _FakeSession:
    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False


async def test_run_login_proactive_delegates_to_coordinator_with_login_trigger(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(db_engine, "async_session_maker", lambda: session)

    calls: list[dict] = []

    async def _fake_run(patient_id, db, *, trigger, **kw):
        calls.append({"patient_id": patient_id, "db": db, "trigger": trigger})
        return []

    monkeypatch.setattr(
        "app.llm.proactive_coordinator.run_proactive_coordination", _fake_run
    )

    await on_login.run_login_proactive(42)

    assert calls == [{"patient_id": 42, "db": session, "trigger": "login"}]


async def test_run_login_proactive_swallows_errors(monkeypatch):
    monkeypatch.setattr(db_engine, "async_session_maker", lambda: _FakeSession())

    async def _boom(*a, **kw):
        raise RuntimeError("coordinator down")

    monkeypatch.setattr(
        "app.llm.proactive_coordinator.run_proactive_coordination", _boom
    )

    # не должно пробросить — вызывается из BackgroundTasks
    await on_login.run_login_proactive(1)
