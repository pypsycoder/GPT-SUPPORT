"""Тесты L1 — kNN по эмбеддингам прототипов.

Реальных прототипов (``router_prototypes.SEED_PROTOTYPES``) и реального
embeddings API здесь нет: подменяем и то, и другое контролируемыми
фикстурами, чтобы точно знать ожидаемые косинусные расстояния — тестируем
логику kNN/threshold/margin, а не качество эмбеддингов GigaChat.
"""

from __future__ import annotations

import pytest

from app.llm import router_l1
from app.llm.errors import LLMTransportError

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]

_FAKE_PROTOTYPES = [
    ("простой вопрос", "simple"),
    ("болит голова", "clinical"),
    ("мне грустно", "emotional"),
]

# Ортогональные векторы — предсказуемая косинусная близость без реальной семантики.
_VECTORS = {
    "простой вопрос": [1.0, 0.0, 0.0],
    "болит голова": [0.0, 1.0, 0.0],
    "мне грустно": [0.0, 0.0, 1.0],
}


@pytest.fixture(autouse=True)
def _reset_prototype_cache(monkeypatch):
    monkeypatch.setattr(router_l1, "SEED_PROTOTYPES", _FAKE_PROTOTYPES)

    async def _fake_batch(texts: list[str]) -> list[list[float]]:
        return [list(_VECTORS.get(t, [0.0, 0.0, 0.0])) for t in texts]

    monkeypatch.setattr(router_l1, "get_text_embeddings_batch", _fake_batch)
    router_l1._prototype_embeddings = None
    yield
    router_l1._prototype_embeddings = None


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

    monkeypatch.setattr(router_l1, "get_text_embedding", _get)

    decision = await router_l1.classify("   ")

    assert decision.request_type is None
    assert not called


async def test_exact_match_resolves_confidently(monkeypatch):
    monkeypatch.setattr(
        router_l1, "get_text_embedding", _fake_embedding_factory({"голова раскалывается": [0.0, 1.0, 0.0]})
    )

    decision = await router_l1.classify("голова раскалывается")

    assert decision.resolved
    assert decision.request_type == "clinical"
    assert decision.confidence == pytest.approx(1.0)


async def test_below_threshold_is_not_resolved(monkeypatch):
    # Почти ортогонален всем трём прототипам — низкая уверенность.
    monkeypatch.setattr(
        router_l1, "get_text_embedding", _fake_embedding_factory({"нечто странное": [0.1, 0.1, 0.1]})
    )

    decision = await router_l1.classify("нечто странное", threshold=0.62)

    assert not decision.resolved
    assert decision.confidence < 0.62


async def test_ambiguous_margin_between_two_classes_is_not_resolved(monkeypatch):
    # Равноудалён от "clinical" и "emotional" — уверенность высокая, но margin нулевой.
    monkeypatch.setattr(
        router_l1,
        "get_text_embedding",
        _fake_embedding_factory({"и то и другое": [0.0, 0.71, 0.71]}),
    )

    decision = await router_l1.classify("и то и другое", threshold=0.62, margin=0.05)

    assert not decision.resolved
    assert decision.margin < 0.05


async def test_provider_error_returns_unresolved_decision_not_raise(monkeypatch):
    async def _raise(text: str) -> list[float]:
        raise LLMTransportError("provider down")

    monkeypatch.setattr(router_l1, "get_text_embedding", _raise)

    decision = await router_l1.classify("что угодно")

    assert decision == router_l1.L1Decision()


async def test_l1_enabled_reads_env_flag(monkeypatch):
    monkeypatch.delenv(router_l1.ENV_FLAG, raising=False)
    assert router_l1.l1_enabled() is False
    monkeypatch.setenv(router_l1.ENV_FLAG, "1")
    assert router_l1.l1_enabled() is True
