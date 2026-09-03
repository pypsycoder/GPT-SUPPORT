from __future__ import annotations

import asyncio
import os

import pytest

from app.llm.errors import LLMConfigurationError
from app.llm.pool import (
    CLOUDRU_DEFAULT_MODEL,
    MODEL_NAMES,
    AccountPool,
    GigaChatClient,
    _SharedAccountState,
    _ascii_only,
)


def _clear_llm_env(monkeypatch) -> None:
    """Убрать из окружения всё, что видит AccountPool — тест сам задаёт конфиг.

    В .env dev-машины есть и GIGACHAT_KEY_*, и CLOUD_RU_KEY; load_environment()
    тащит их в os.environ до импорта тестов.
    """
    for name in list(os.environ):
        if (
            name.startswith("GIGACHAT_KEY_")
            or name.startswith("GIGACHAT_MODEL_")
            or name.startswith("CLOUD_RU_")
        ):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


def test_ascii_only_strips_non_ascii_characters():
    assert _ascii_only("abc-ключ-123") == "abc--123"


def test_account_pool_raises_when_no_accounts_configured(monkeypatch):
    _clear_llm_env(monkeypatch)

    pool = AccountPool()

    assert pool.clients == []
    assert pool.account_count == 0
    with pytest.raises(LLMConfigurationError, match="No LLM accounts configured"):
        asyncio.run(pool.get_available("lite"))


def test_single_key_serves_all_tiers_on_one_lock(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGACHAT_KEY_A1", "abc123")

    pool = AccountPool()

    assert {client.model_tier for client in pool.clients} == set(MODEL_NAMES)
    # один аккаунт → один общий лок на все тиры → конкурентность 1
    assert pool.account_count == 1
    assert len({id(c._state) for c in pool.clients}) == 1


def test_two_keys_double_the_concurrency_and_each_serves_all_tiers(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGACHAT_KEY_A1", "dima-key")
    monkeypatch.setenv("GIGACHAT_KEY_L1", "lena-key")

    pool = AccountPool()

    assert pool.account_count == 2
    # каждый аккаунт поднят под все три тира
    per_account_tiers: dict[str, set[str]] = {}
    for client in pool.clients:
        base = client.account_id.rsplit("-", 1)[0]
        per_account_tiers.setdefault(base, set()).add(client.model_tier)
    assert per_account_tiers == {"A1": set(MODEL_NAMES), "L1": set(MODEL_NAMES)}
    # тир-алиасы одного аккаунта делят один лок
    a1_states = {id(c._state) for c in pool.clients if c.account_id.startswith("A1")}
    l1_states = {id(c._state) for c in pool.clients if c.account_id.startswith("L1")}
    assert len(a1_states) == 1 and len(l1_states) == 1 and a1_states != l1_states


def test_duplicate_key_value_collapses_to_one_account(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGACHAT_KEY_A1", "same-key")
    monkeypatch.setenv("GIGACHAT_KEY_A2", "same-key")

    pool = AccountPool()

    assert pool.account_count == 1


def test_gigachat_model_override_pins_account_to_one_tier(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGACHAT_KEY_A1", "key-a1")
    monkeypatch.setenv("GIGACHAT_MODEL_A1", "max")

    pool = AccountPool()

    assert [c.model_tier for c in pool.clients] == ["max"]
    # без тир-суффикса, раз тир один
    assert [c.account_id for c in pool.clients] == ["A1"]


def test_account_order_is_deterministic(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGACHAT_KEY_L1", "lena-key")
    monkeypatch.setenv("GIGACHAT_KEY_A1", "dima-key")

    first = [c.account_id for c in AccountPool().clients]
    second = [c.account_id for c in AccountPool().clients]

    assert first == second
    assert first[0].startswith("A1")  # отсортировано по account_id, не по порядку env


@pytest.mark.asyncio
async def test_sticky_routing_pins_a_thread_to_one_account_across_tiers(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GIGACHAT_KEY_A1", "dima-key")
    monkeypatch.setenv("GIGACHAT_KEY_L1", "lena-key")

    pool = AccountPool()

    key = "p42-thread-abc"
    pro = await pool.get_available("pro", sticky_key=key)
    mx = await pool.get_available("max", sticky_key=key)

    assert pro.model_tier == "pro" and mx.model_tier == "max"
    assert pro.account_id.rsplit("-", 1)[0] == mx.account_id.rsplit("-", 1)[0]


def test_shared_state_lock_drives_busy_status():
    state = _SharedAccountState(api_key="abc")
    client = GigaChatClient("A1", "abc", "lite", shared_state=state)

    assert client.is_busy is False

    async def _locked() -> bool:
        async with state.lock:
            return client.is_busy

    assert asyncio.run(_locked()) is True


# ── LLM_PROVIDER=cloudru ────────────────────────────────────────────────────

def test_cloudru_provider_builds_openai_compatible_clients(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "cloudru")
    monkeypatch.setenv("CLOUD_RU_KEY", "keyid.secret")

    pool = AccountPool()

    assert pool.chat_provider == "cloudru"
    cloud = [c for c in pool.clients if c.provider.name == "cloudru"]
    assert {c.model_tier for c in cloud} == set(MODEL_NAMES)
    assert {c.account_id for c in cloud} == {"cloudru-lite", "cloudru-pro", "cloudru-max"}
    # один ключ = один общий стейт (семафор) на все тиры
    assert len({id(c._state) for c in cloud}) == 1
    for c in cloud:
        assert c.provider.auth_url is None                  # без OAuth
        assert c.provider.model_for(c.model_tier) == CLOUDRU_DEFAULT_MODEL
        assert c.provider.send_session_header is False

    client = asyncio.run(pool.get_available("lite"))
    assert client.provider.name == "cloudru"


def test_cloudru_access_token_is_the_raw_key(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "cloudru")
    monkeypatch.setenv("CLOUD_RU_KEY", "keyid.secret")

    pool = AccountPool()
    client = asyncio.run(pool.get_available("pro"))
    # никакого сетевого обмена — ключ и есть Bearer
    assert asyncio.run(client._get_access_token()) == "keyid.secret"


def test_cloudru_model_override_targets_one_tier(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "cloudru")
    monkeypatch.setenv("CLOUD_RU_KEY", "keyid.secret")
    monkeypatch.setenv("CLOUD_RU_MODEL_LITE", "ai-sage/GigaChat3-10B-A1.8B")

    pool = AccountPool()
    by_tier = {c.model_tier: c.provider.model_for(c.model_tier) for c in pool.clients}
    assert by_tier["lite"] == "ai-sage/GigaChat3-10B-A1.8B"
    assert by_tier["pro"] == CLOUDRU_DEFAULT_MODEL


def test_both_providers_coexist_and_embeddings_can_pin_sber(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "cloudru")
    monkeypatch.setenv("CLOUD_RU_KEY", "keyid.secret")
    monkeypatch.setenv("GIGACHAT_KEY_A1", "sber-key")

    pool = AccountPool()

    # чат по умолчанию — cloudru
    assert asyncio.run(pool.get_available("lite")).provider.name == "cloudru"
    # эмбеддинги явно фиксируют Сбер
    assert asyncio.run(pool.get_available("lite", provider="sber")).provider.name == "sber"


def test_pinned_provider_without_account_raises(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "cloudru")
    monkeypatch.setenv("CLOUD_RU_KEY", "keyid.secret")

    pool = AccountPool()
    with pytest.raises(LLMConfigurationError, match="No 'sber' LLM account"):
        asyncio.run(pool.get_available("lite", provider="sber"))


def test_proactive_concurrency_follows_active_provider(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("CLOUD_RU_KEY", "keyid.secret")
    monkeypatch.setenv("CLOUD_RU_CONCURRENCY", "12")
    monkeypatch.setenv("GIGACHAT_KEY_A1", "sber-key")

    monkeypatch.setenv("LLM_PROVIDER", "sber")
    assert AccountPool().proactive_concurrency == 1        # один сбер-ключ

    monkeypatch.setenv("LLM_PROVIDER", "cloudru")
    assert AccountPool().proactive_concurrency == 12       # CLOUD_RU_CONCURRENCY


def test_unknown_provider_falls_back_to_sber(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("GIGACHAT_KEY_A1", "sber-key")

    pool = AccountPool()
    assert pool.chat_provider == "sber"
