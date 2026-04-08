from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.llm.worker as worker


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


async def test_run_worker_requires_explicit_scheduler_flag(monkeypatch):
    monkeypatch.setattr(worker, "settings", SimpleNamespace(scheduler_enabled=False, scheduler_lock_id=1))

    with pytest.raises(RuntimeError, match="SCHEDULER_ENABLED=true"):
        await worker.run_worker()


async def test_run_worker_exits_when_scheduler_lock_is_busy(monkeypatch):
    monkeypatch.setattr(worker, "settings", SimpleNamespace(scheduler_enabled=True, scheduler_lock_id=1))
    monkeypatch.setattr(worker, "acquire_scheduler_lock", AsyncMock(return_value=False))
    start_scheduler = Mock()
    monkeypatch.setattr(worker, "start_scheduler", start_scheduler)

    await worker.run_worker()

    start_scheduler.assert_not_called()
