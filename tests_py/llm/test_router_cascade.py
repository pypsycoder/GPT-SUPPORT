"""Тесты оркестрации каскада L0 → L1 → L2 → откат на старый роутер."""

from __future__ import annotations

import pytest

from app.llm import router_cascade, router_l0, router_l1, router_l2
from app.llm.router import ModelTier, RequestType

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


def _disable_all(monkeypatch):
    monkeypatch.setattr(router_l0, "l0_enabled", lambda: False)
    monkeypatch.setattr(router_l1, "l1_enabled", lambda: False)
    monkeypatch.setattr(router_l2, "l2_enabled", lambda: False)


async def test_l0_alone_fixes_bp_false_positive_without_l1_l2(monkeypatch):
    """Регрессия, пойманная при написании MANUAL_TEST_PLAN.md: с ОДНИМ
    LLM_ROUTER_L0=1 (L1/L2 выключены) "давление 200 на 100" раньше проваливалось
    в старый classify_request и оставалось SAFETY — L0 резолвил data_entry,
    но каскад это игнорировал, консультируя только safety_level. Использует
    настоящий router_l0.classify (не мок): регрессия была именно в связке."""
    monkeypatch.setattr(router_l0, "l0_enabled", lambda: True)
    monkeypatch.setattr(router_l1, "l1_enabled", lambda: False)
    monkeypatch.setattr(router_l2, "l2_enabled", lambda: False)

    result = await router_cascade.classify_request_async("У меня давление 200 на 100", "text")

    assert result.request_type == RequestType.CLINICAL
    assert result.model_tier == ModelTier.PRO


async def test_button_source_bypasses_cascade_entirely(monkeypatch):
    calls = []
    monkeypatch.setattr(router_l0, "l0_enabled", lambda: (calls.append("l0") or True))

    result = await router_cascade.classify_request_async("неважно", "button")

    assert result.request_type == RequestType.QUICK_ACTION
    assert calls == []  # каскад не звался вовсе


async def test_l0_urgent_short_circuits_before_l1_l2(monkeypatch):
    monkeypatch.setattr(router_l0, "l0_enabled", lambda: True)
    monkeypatch.setattr(
        router_l0, "classify", lambda text, **kw: router_l0.L0Decision(
            intent="safety", safety_level="urgent", safety_kind="psychological", rule="test"
        )
    )
    l1_called = False
    l2_called = False

    async def _l1_should_not_be_called(text):
        nonlocal l1_called
        l1_called = True
        return router_l1.L1Decision()

    monkeypatch.setattr(router_l1, "l1_enabled", lambda: True)
    monkeypatch.setattr(router_l1, "classify", _l1_should_not_be_called)
    monkeypatch.setattr(router_l2, "l2_enabled", lambda: True)

    async def _l2_should_not_be_called(text):
        nonlocal l2_called
        l2_called = True
        return None

    monkeypatch.setattr(router_l2, "classify", _l2_should_not_be_called)

    result = await router_cascade.classify_request_async("угроза", "text")

    assert result.request_type == RequestType.SAFETY
    assert result.model_tier == ModelTier.MAX
    assert result.priority == 3
    assert not l1_called
    assert not l2_called


async def test_l0_concern_raises_floor_but_keeps_l1_request_type(monkeypatch):
    monkeypatch.setattr(router_l0, "l0_enabled", lambda: True)
    monkeypatch.setattr(
        router_l0, "classify", lambda text, **kw: router_l0.L0Decision(safety_level="concern", rule="exhaustion")
    )
    monkeypatch.setattr(router_l1, "l1_enabled", lambda: True)

    async def _fake_l1(text):
        return router_l1.L1Decision(request_type="simple", confidence=0.9, margin=0.2)

    monkeypatch.setattr(router_l1, "classify", _fake_l1)
    monkeypatch.setattr(router_l2, "l2_enabled", lambda: False)

    result = await router_cascade.classify_request_async("больше не могу это выносить", "text")

    # request_type остаётся simple (L1 не ошибся), но тир/приоритет подняты полом.
    assert result.request_type == RequestType.SIMPLE
    assert result.model_tier == ModelTier.PRO
    assert result.priority == 2


async def test_l1_resolves_when_l0_does_not(monkeypatch):
    _disable_all(monkeypatch)
    monkeypatch.setattr(router_l1, "l1_enabled", lambda: True)

    async def _fake_l1(text):
        return router_l1.L1Decision(request_type="clinical", confidence=0.9, margin=0.2)

    monkeypatch.setattr(router_l1, "classify", _fake_l1)

    l2_called = False

    async def _l2_should_not_be_called(text):
        nonlocal l2_called
        l2_called = True
        return None

    monkeypatch.setattr(router_l2, "l2_enabled", lambda: True)
    monkeypatch.setattr(router_l2, "classify", _l2_should_not_be_called)

    result = await router_cascade.classify_request_async("что-то про самочувствие", "text")

    assert result.request_type == RequestType.CLINICAL
    assert result.model_tier == ModelTier.PRO
    assert not l2_called


async def test_l2_resolves_when_l0_and_l1_do_not(monkeypatch):
    _disable_all(monkeypatch)
    monkeypatch.setattr(router_l2, "l2_enabled", lambda: True)

    async def _fake_l2(text):
        return "emotional"

    monkeypatch.setattr(router_l2, "classify", _fake_l2)

    result = await router_cascade.classify_request_async("непонятная реплика", "text")

    assert result.request_type == RequestType.EMOTIONAL
    assert result.model_tier == ModelTier.PRO


async def test_l2_can_flag_safety_even_without_l0_urgent(monkeypatch):
    _disable_all(monkeypatch)
    monkeypatch.setattr(router_l2, "l2_enabled", lambda: True)

    async def _fake_l2(text):
        return "safety"

    monkeypatch.setattr(router_l2, "classify", _fake_l2)

    result = await router_cascade.classify_request_async("двусмысленная фраза", "text")

    assert result.request_type == RequestType.SAFETY
    assert result.model_tier == ModelTier.MAX
    assert result.priority == 3


async def test_everything_disabled_falls_back_to_sync_classifier(monkeypatch):
    _disable_all(monkeypatch)

    result = await router_cascade.classify_request_async("давление 200 на 100", "text")

    # Синхронный classify_request жив и работает как раньше (со своими
    # старыми недостатками) — каскад просто выключен целиком.
    assert result.request_type == RequestType.SAFETY


async def test_l1_exception_falls_back_gracefully(monkeypatch):
    _disable_all(monkeypatch)
    monkeypatch.setattr(router_l1, "l1_enabled", lambda: True)

    async def _boom(text):
        raise RuntimeError("unexpected bug")

    monkeypatch.setattr(router_l1, "classify", _boom)

    # Не должно бросить исключение наружу.
    result = await router_cascade.classify_request_async("привет", "text")

    assert result is not None


async def test_system_source_maps_to_proactive_when_unresolved(monkeypatch):
    _disable_all(monkeypatch)

    result = await router_cascade.classify_request_async("напоминание", "system")

    assert result.request_type == RequestType.PROACTIVE
    assert result.model_tier == ModelTier.PRO
    assert result.priority == 1


async def test_system_source_relabeled_proactive_keeps_old_tier_even_when_short(monkeypatch):
    """Регрессия code review: старый classify_request всегда отдавал PRO для
    source == "system", независимо от длины текста. _map_request_type("simple", ...)
    для короткого текста отдаёт LITE — релейбл на PROACTIVE обязан это перебить."""
    _disable_all(monkeypatch)
    monkeypatch.setattr(router_l1, "l1_enabled", lambda: True)

    async def _fake_l1(text):
        return router_l1.L1Decision(request_type="simple", confidence=0.9, margin=0.2)

    monkeypatch.setattr(router_l1, "classify", _fake_l1)

    result = await router_cascade.classify_request_async("ок", "system")  # короче 30 символов

    assert result.request_type == RequestType.PROACTIVE
    assert result.model_tier == ModelTier.PRO
    assert result.priority == 1
