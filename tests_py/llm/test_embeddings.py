"""Тесты общего клиента эмбеддингов (``app/llm/embeddings.py``).

Регрессии code review: неограниченный кэш эмбеддингов (раньше только под
RAG-запросы с реальным повтором, теперь ещё и под router_l1 на почти всегда
уникальных репликах пациента) и последовательные эмбеддинги прототипов L1
вместо одного batched-запроса.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm import embeddings
from app.llm.errors import LLMResponseError

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clean_cache():
    embeddings._EMBEDDING_CACHE.clear()
    yield
    embeddings._EMBEDDING_CACHE.clear()


def _fake_pool(response: dict):
    fake_client = SimpleNamespace(_get_access_token=AsyncMock(return_value="tok"))
    return SimpleNamespace(get_available=AsyncMock(return_value=fake_client))


async def test_get_text_embedding_caches_by_text(monkeypatch):
    fake_post = AsyncMock(return_value={"data": [{"embedding": [1.0, 2.0]}]})
    monkeypatch.setattr("app.llm.embeddings.request_json_with_policy", fake_post)
    monkeypatch.setattr("app.llm.pool.pool", _fake_pool({}))

    first = await embeddings.get_text_embedding("привет")
    second = await embeddings.get_text_embedding("привет")

    assert first == [1.0, 2.0]
    assert second == [1.0, 2.0]
    fake_post.assert_awaited_once()  # второй вызов — из кэша, без сети


async def test_cache_is_bounded_and_evicts_least_recently_used(monkeypatch):
    monkeypatch.setattr(embeddings, "_EMBEDDING_CACHE_MAX_SIZE", 2)
    responses = iter(
        [
            {"data": [{"embedding": [1.0]}]},
            {"data": [{"embedding": [2.0]}]},
            {"data": [{"embedding": [3.0]}]},
        ]
    )

    async def fake_post(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr("app.llm.embeddings.request_json_with_policy", fake_post)
    monkeypatch.setattr("app.llm.pool.pool", _fake_pool({}))

    await embeddings.get_text_embedding("a")
    await embeddings.get_text_embedding("b")
    # "a" остаётся самой свежей после этого обращения — вытеснится "b", не "a".
    await embeddings.get_text_embedding("a")
    await embeddings.get_text_embedding("c")  # переполняет потолок в 2

    assert len(embeddings._EMBEDDING_CACHE) == 2
    assert "a" in embeddings._EMBEDDING_CACHE
    assert "c" in embeddings._EMBEDDING_CACHE
    assert "b" not in embeddings._EMBEDDING_CACHE


async def test_batch_sends_one_request_and_preserves_order(monkeypatch):
    fake_post = AsyncMock(
        return_value={
            "data": [
                {"index": 1, "embedding": [2.0]},
                {"index": 0, "embedding": [1.0]},
            ]
        }
    )
    monkeypatch.setattr("app.llm.embeddings.request_json_with_policy", fake_post)
    monkeypatch.setattr("app.llm.pool.pool", _fake_pool({}))

    result = await embeddings.get_text_embeddings_batch(["первый", "второй"])

    assert result == [[1.0], [2.0]]
    fake_post.assert_awaited_once()
    assert fake_post.call_args.kwargs["json_body"]["input"] == ["первый", "второй"]


async def test_batch_skips_already_cached_texts(monkeypatch):
    embeddings._EMBEDDING_CACHE["уже есть"] = [9.0]
    fake_post = AsyncMock(return_value={"data": [{"index": 0, "embedding": [1.0]}]})
    monkeypatch.setattr("app.llm.embeddings.request_json_with_policy", fake_post)
    monkeypatch.setattr("app.llm.pool.pool", _fake_pool({}))

    result = await embeddings.get_text_embeddings_batch(["уже есть", "новый"])

    assert result == [[9.0], [1.0]]
    assert fake_post.call_args.kwargs["json_body"]["input"] == ["новый"]


async def test_batch_all_cached_makes_no_network_call(monkeypatch):
    embeddings._EMBEDDING_CACHE["a"] = [1.0]
    embeddings._EMBEDDING_CACHE["b"] = [2.0]
    fake_post = AsyncMock()
    monkeypatch.setattr("app.llm.embeddings.request_json_with_policy", fake_post)

    result = await embeddings.get_text_embeddings_batch(["a", "b"])

    assert result == [[1.0], [2.0]]
    fake_post.assert_not_called()


async def test_batch_size_mismatch_raises(monkeypatch):
    fake_post = AsyncMock(return_value={"data": [{"index": 0, "embedding": [1.0]}]})  # только 1 вместо 2
    monkeypatch.setattr("app.llm.embeddings.request_json_with_policy", fake_post)
    monkeypatch.setattr("app.llm.pool.pool", _fake_pool({}))

    with pytest.raises(LLMResponseError):
        await embeddings.get_text_embeddings_batch(["один", "два"])
