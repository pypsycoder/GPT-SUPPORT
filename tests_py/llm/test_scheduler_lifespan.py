from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

import app.llm.scheduler as scheduler_mod
import app.llm.technique_library as technique_library
from app.main import lifespan


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest.fixture
def scheduler_spies(monkeypatch):
    spies = {
        "start": Mock(),
        "stop": Mock(),
        "acquire": AsyncMock(return_value=True),
        "release": AsyncMock(),
    }
    monkeypatch.setattr(scheduler_mod, "start_scheduler", spies["start"])
    monkeypatch.setattr(scheduler_mod, "stop_scheduler", spies["stop"])
    monkeypatch.setattr(scheduler_mod, "acquire_scheduler_lock", spies["acquire"])
    monkeypatch.setattr(scheduler_mod, "release_scheduler_lock", spies["release"])
    # Не ходить в БД за карточками техник — предмет теста в другом.
    monkeypatch.setattr(technique_library, "refresh_technique_cache", AsyncMock(return_value=0))
    return spies


async def test_lifespan_starts_scheduler_when_enabled(monkeypatch, scheduler_spies):
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")

    async with lifespan(None):
        scheduler_spies["acquire"].assert_awaited_once()
        scheduler_spies["start"].assert_called_once()
        scheduler_spies["stop"].assert_not_called()

    # Остановка и снятие lock — на shutdown.
    scheduler_spies["stop"].assert_called_once()
    scheduler_spies["release"].assert_awaited_once()


async def test_lifespan_skips_scheduler_when_disabled(monkeypatch, scheduler_spies):
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")

    async with lifespan(None):
        pass

    scheduler_spies["acquire"].assert_not_awaited()
    scheduler_spies["start"].assert_not_called()
    scheduler_spies["stop"].assert_not_called()
    scheduler_spies["release"].assert_not_awaited()


async def test_lifespan_does_not_start_when_lock_is_busy(monkeypatch, scheduler_spies):
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    scheduler_spies["acquire"].return_value = False

    async with lifespan(None):
        pass

    scheduler_spies["acquire"].assert_awaited_once()
    scheduler_spies["start"].assert_not_called()
    # lock не взят — освобождать нечего.
    scheduler_spies["stop"].assert_not_called()
    scheduler_spies["release"].assert_not_awaited()
