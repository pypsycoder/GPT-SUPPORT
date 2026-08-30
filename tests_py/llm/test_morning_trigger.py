from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import core.db.engine as db_engine
from app.llm import morning_service


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


class _FakeSession:
    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False


@pytest.fixture
def fake_session(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(db_engine, "async_session_maker", lambda: session)
    return session


async def test_ensure_morning_message_bg_opens_own_session(monkeypatch, fake_session):
    inner = AsyncMock()
    monkeypatch.setattr(morning_service, "ensure_morning_message", inner)

    await morning_service.ensure_morning_message_bg(42)

    inner.assert_awaited_once_with(42, fake_session)


async def test_ensure_morning_message_bg_swallows_errors(monkeypatch, fake_session):
    inner = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(morning_service, "ensure_morning_message", inner)

    # Не должно пробросить — вызывается из BackgroundTasks.
    await morning_service.ensure_morning_message_bg(1)

    inner.assert_awaited_once()
