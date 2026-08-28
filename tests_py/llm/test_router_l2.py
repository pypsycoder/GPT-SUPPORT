"""Тесты L2 — Lite + structured output, последний уровень каскада."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm import router_l2
from app.llm.errors import LLMResponseError
from app.llm.pool import StructuredResult

pytestmark = [pytest.mark.unit]


async def test_empty_text_short_circuits_without_calling_pool(monkeypatch):
    fake_pool = SimpleNamespace(get_available=AsyncMock())
    monkeypatch.setattr("app.llm.pool.pool", fake_pool)

    result = await router_l2.classify("   ")

    assert result is None
    fake_pool.get_available.assert_not_called()


async def test_successful_call_returns_request_type_and_uses_shared_session(monkeypatch):
    fake_client = SimpleNamespace(
        structured=AsyncMock(
            return_value=StructuredResult(
                parsed=router_l2.RouterL2Reply(request_type="clinical"),
                raw_text="",
            )
        )
    )
    fake_pool = SimpleNamespace(get_available=AsyncMock(return_value=fake_client))
    monkeypatch.setattr("app.llm.pool.pool", fake_pool)

    result = await router_l2.classify("болит голова после диализа")

    assert result == "clinical"
    fake_pool.get_available.assert_awaited_once_with("lite")
    _, kwargs = fake_client.structured.call_args
    assert kwargs["session_id"] == router_l2.SHARED_SESSION_ID


async def test_provider_error_returns_none_not_raise(monkeypatch):
    fake_client = SimpleNamespace(
        structured=AsyncMock(side_effect=LLMResponseError("bad json"))
    )
    fake_pool = SimpleNamespace(get_available=AsyncMock(return_value=fake_client))
    monkeypatch.setattr("app.llm.pool.pool", fake_pool)

    result = await router_l2.classify("что угодно")

    assert result is None


def test_schema_rejects_out_of_enum_request_type():
    with pytest.raises(ValueError):
        router_l2.RouterL2Reply(request_type="not_a_real_type")
