"""Тесты crisis_semantic — kNN по эмбеддингам для суицидального риска.

Тот же подход, что test_router_l1.py: подменяем прототипы и embeddings
API контролируемыми фикстурами (ортогональные векторы), тестируем логику
threshold/margin, а не качество эмбеддингов GigaChat.
"""

from __future__ import annotations

import pytest

from app.llm import crisis_semantic
from app.llm.errors import LLMTransportError

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]

_FAKE_POSITIVE = ["хочу умереть"]
_FAKE_NEGATIVE = ["устал от работы", "давление 120 на 80"]

_VECTORS = {
    "хочу умереть": [1.0, 0.0, 0.0],
    "устал от работы": [0.0, 1.0, 0.0],
    "давление 120 на 80": [0.0, 0.0, 1.0],
}


@pytest.fixture(autouse=True)
def _reset_prototype_cache(monkeypatch):
    monkeypatch.setattr(crisis_semantic, "POSITIVE_MINED", _FAKE_POSITIVE)
    monkeypatch.setattr(crisis_semantic, "POSITIVE_DRAFTED", [])
    monkeypatch.setattr(crisis_semantic, "NEGATIVE_MINED", _FAKE_NEGATIVE)

    async def _fake_batch(texts: list[str]) -> list[list[float]]:
        return [list(_VECTORS.get(t, [0.0, 0.0, 0.0])) for t in texts]

    monkeypatch.setattr(crisis_semantic, "get_text_embeddings_batch", _fake_batch)
    crisis_semantic._prototype_vectors = None
    yield
    crisis_semantic._prototype_vectors = None


def _fake_embedding_factory(overrides: dict[str, list[float]]):
    async def _get(text: str) -> list[float]:
        if text in _VECTORS:
            return list(_VECTORS[text])
        if text in overrides:
            return list(overrides[text])
        return [0.0, 0.0, 0.0]

    return _get


async def test_empty_text_short_circuits_without_calling_embeddings(monkeypatch):
    called = False

    async def _get(text: str) -> list[float]:
        nonlocal called
        called = True
        return [0.0, 0.0, 0.0]

    monkeypatch.setattr(crisis_semantic, "get_text_embedding", _get)

    decision = await crisis_semantic.classify("   ")

    assert not decision.is_crisis
    assert not called


async def test_paraphrase_close_to_positive_prototype_fires(monkeypatch):
    # Не точное совпадение со словарём — семантически близко к позитиву,
    # далеко от обоих негативов. Это и есть сценарий, ради которого слой
    # существует: перефразировка, которую не поймал бы буквальный regex.
    monkeypatch.setattr(
        crisis_semantic,
        "get_text_embedding",
        _fake_embedding_factory({"хочу перестать существовать": [0.95, 0.05, 0.05]}),
    )

    decision = await crisis_semantic.classify(
        "хочу перестать существовать", threshold=0.7, margin=0.01
    )

    assert decision.is_crisis
    assert decision.nearest_positive == "хочу умереть"


async def test_below_threshold_does_not_fire(monkeypatch):
    monkeypatch.setattr(
        crisis_semantic,
        "get_text_embedding",
        _fake_embedding_factory({"нечто странное": [0.1, 0.1, 0.1]}),
    )

    decision = await crisis_semantic.classify("нечто странное", threshold=0.7, margin=0.01)

    assert not decision.is_crisis
    assert decision.confidence < 0.7


async def test_closer_to_negative_than_positive_does_not_fire(monkeypatch):
    # Похоже и на позитив, и на негатив примерно одинаково (margin мал) —
    # неуверенность не должна подменяться срабатыванием.
    monkeypatch.setattr(
        crisis_semantic,
        "get_text_embedding",
        _fake_embedding_factory({"и то и другое": [0.71, 0.71, 0.0]}),
    )

    decision = await crisis_semantic.classify("и то и другое", threshold=0.5, margin=0.05)

    assert not decision.is_crisis
    assert decision.margin < 0.05


async def test_negative_prototype_itself_does_not_fire(monkeypatch):
    monkeypatch.setattr(
        crisis_semantic,
        "get_text_embedding",
        _fake_embedding_factory({"устал от работы": [0.0, 1.0, 0.0]}),
    )

    decision = await crisis_semantic.classify("устал от работы")

    assert not decision.is_crisis


async def test_provider_error_returns_non_crisis_not_raise(monkeypatch):
    async def _raise(text: str) -> list[float]:
        raise LLMTransportError("provider down")

    monkeypatch.setattr(crisis_semantic, "get_text_embedding", _raise)

    decision = await crisis_semantic.classify("что угодно")

    assert decision == crisis_semantic.CrisisSemanticDecision()


async def test_crisis_semantic_enabled_reads_env_flag(monkeypatch):
    monkeypatch.delenv(crisis_semantic.ENV_FLAG, raising=False)
    assert crisis_semantic.crisis_semantic_enabled() is False
    monkeypatch.setenv(crisis_semantic.ENV_FLAG, "1")
    assert crisis_semantic.crisis_semantic_enabled() is True
