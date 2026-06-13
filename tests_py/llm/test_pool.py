from __future__ import annotations

import pytest

from app.llm.errors import LLMConfigurationError
from app.llm.pool import AccountPool, GigaChatClient, MODEL_NAMES, _SharedAccountState, _ascii_only


def test_ascii_only_strips_non_ascii_characters():
    assert _ascii_only("abc-ключ-123") == "abc--123"


def test_account_pool_raises_when_no_accounts_configured(monkeypatch):
    for index in range(1, 20):
        monkeypatch.delenv(f"GIGACHAT_KEY_A{index}", raising=False)

    pool = AccountPool()

    with pytest.raises(LLMConfigurationError, match="No GigaChat accounts configured"):
        import asyncio

        asyncio.run(pool.get_available("lite"))


def test_account_pool_adds_shared_tier_aliases_for_single_key(monkeypatch):
    for index in range(1, 20):
        monkeypatch.delenv(f"GIGACHAT_KEY_A{index}", raising=False)
        monkeypatch.delenv(f"GIGACHAT_MODEL_A{index}", raising=False)
    monkeypatch.setenv("GIGACHAT_KEY_A1", "abc123")

    pool = AccountPool()

    assert {client.model_tier for client in pool.clients} == set(MODEL_NAMES)


def test_shared_state_lock_drives_busy_status():
    state = _SharedAccountState(api_key="abc")
    client = GigaChatClient("A1", "abc", "lite", shared_state=state)

    assert client.is_busy is False

    async def _locked() -> bool:
        async with state.lock:
            return client.is_busy

    import asyncio

    assert asyncio.run(_locked()) is True
