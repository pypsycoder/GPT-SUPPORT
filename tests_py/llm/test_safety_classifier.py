"""LLM-классификатор суицид-риска (2-й эшелон после L0) + его ветка в boundary_guard.

Golden-регрессия (прогон против tests/fixtures/safety_golden.jsonl) — отдельно,
в test_safety_classifier_golden.py, под skipif без ключа GigaChat.
"""

from __future__ import annotations

import pytest

from app.llm import safety_classifier
from app.llm.pipeline.stages.boundary_guard import BoundaryGuardStage
from app.llm.pipeline.types import PipelineContext
from app.llm.safety_classifier import SafetyAssessment
from app.llm.safety_responses import (
    CRISIS_RESPONSE,
    SAFETY_FOOTER_ACTIVE,
    SAFETY_FOOTER_PASSIVE,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.unit, pytest.mark.real_safety_classifier]


# --------------------------------------------------------------------------- #
# Модуль safety_classifier
# --------------------------------------------------------------------------- #

class _FakeStructuredResult:
    def __init__(self, card):
        self.parsed = card
        self.latency_ms = 123


class _FakeCard:
    def __init__(self, level, subject="self", confidence=0.9):
        self.level = level
        self.subject = subject
        self.confidence = confidence


def _mock_pool(monkeypatch, *, card=None, exc=None):
    class _Client:
        async def structured(self, messages, system_prompt, schema, **kwargs):
            if exc is not None:
                raise exc
            return _FakeStructuredResult(card)

    async def _get_available(tier, **kwargs):
        return _Client()

    from app.llm import pool as pool_mod

    monkeypatch.setattr(pool_mod.pool, "get_available", _get_available)


async def test_classify_maps_fields(monkeypatch):
    _mock_pool(monkeypatch, card=_FakeCard("plan_or_imminent", "self", 0.95))
    a = await safety_classifier.classify("...")
    assert a.available and a.level == "plan_or_imminent" and a.is_self
    assert a.interrupt and not a.active_ideation
    assert a.latency_ms == 123


async def test_classify_active_and_passive_flags(monkeypatch):
    _mock_pool(monkeypatch, card=_FakeCard("ideation_active"))
    a = await safety_classifier.classify("хочу себя убить")
    assert a.active_ideation and not a.interrupt and not a.passive_ideation

    _mock_pool(monkeypatch, card=_FakeCard("ideation_passive"))
    b = await safety_classifier.classify("лучше бы не просыпаться")
    assert b.passive_ideation and not b.interrupt and not b.active_ideation


async def test_classify_subject_other_is_not_self_risk(monkeypatch):
    _mock_pool(monkeypatch, card=_FakeCard("plan_or_imminent", subject="other"))
    a = await safety_classifier.classify("брат сказал что купил таблетки")
    assert a.available and not a.is_self
    assert not a.interrupt and not a.active_ideation and not a.passive_ideation


async def test_classify_api_error_is_unavailable(monkeypatch):
    from app.llm.errors import LLMResponseError

    _mock_pool(monkeypatch, exc=LLMResponseError("boom"))
    a = await safety_classifier.classify("что угодно")
    assert not a.available and not a.interrupt


async def test_classify_empty_text_short_circuits(monkeypatch):
    a = await safety_classifier.classify("   ")
    assert not a.available


async def test_enabled_default_on_and_kill_switch(monkeypatch):
    monkeypatch.delenv(safety_classifier.ENV_FLAG, raising=False)
    assert safety_classifier.enabled() is True
    monkeypatch.setenv(safety_classifier.ENV_FLAG, "false")
    assert safety_classifier.enabled() is False
    monkeypatch.setenv(safety_classifier.ENV_FLAG, "1")
    assert safety_classifier.enabled() is True


# --------------------------------------------------------------------------- #
# Ветка в BoundaryGuardStage
# --------------------------------------------------------------------------- #

def _ctx(user_input: str) -> PipelineContext:
    from app.llm.pipeline.types import LLMRequest

    return PipelineContext(request=LLMRequest(patient_id=1, user_input=user_input, db=None))


def _stub_classify(monkeypatch, assessment: SafetyAssessment):
    async def _fake(text, context=None):
        return assessment

    monkeypatch.setattr(
        "app.llm.pipeline.stages.boundary_guard.safety_classifier.classify", _fake
    )


async def test_boundary_guard_plan_interrupts(monkeypatch):
    _stub_classify(monkeypatch, SafetyAssessment(level="plan_or_imminent", subject="self", available=True))
    ctx = await BoundaryGuardStage().process(_ctx("мне надоело, всё решено"))
    assert ctx.early_response == CRISIS_RESPONSE
    assert ctx.early_response_source == "boundary_guard_safety_llm"
    assert ctx.diagnostics["boundary_guard"]["action"] == "interrupt"


async def test_boundary_guard_active_sets_hard_footer_and_concern(monkeypatch):
    # вход подобран так, что L0 его НЕ ловит — решает классификатор
    _stub_classify(monkeypatch, SafetyAssessment(level="ideation_active", subject="self", available=True))
    ctx = await BoundaryGuardStage().process(_ctx("последнее время совсем накрывает, не знаю"))
    assert ctx.early_response is None
    assert ctx.safety_footer == SAFETY_FOOTER_ACTIVE
    assert ctx.l0.safety_level == "concern"
    assert ctx.diagnostics["boundary_guard"]["action"] == "footer"


async def test_boundary_guard_passive_sets_soft_footer(monkeypatch):
    _stub_classify(monkeypatch, SafetyAssessment(level="ideation_passive", subject="self", available=True))
    ctx = await BoundaryGuardStage().process(_ctx("зачем всё это продолжать"))
    assert ctx.safety_footer == SAFETY_FOOTER_PASSIVE
    assert ctx.l0.safety_level == "concern"


async def test_boundary_guard_distress_only_concern_no_footer(monkeypatch):
    _stub_classify(monkeypatch, SafetyAssessment(level="distress", subject="self", available=True))
    ctx = await BoundaryGuardStage().process(_ctx("руки опускаются, больше не могу"))
    assert ctx.safety_footer is None
    assert ctx.l0.safety_level == "concern"
    assert ctx.diagnostics["boundary_guard"]["action"] == "hint"


async def test_boundary_guard_other_subject_does_nothing(monkeypatch):
    _stub_classify(monkeypatch, SafetyAssessment(level="plan_or_imminent", subject="other", available=True))
    ctx = await BoundaryGuardStage().process(_ctx("брат купил таблетки и знает сколько нужно"))
    assert ctx.early_response is None and ctx.safety_footer is None
    assert ctx.diagnostics["boundary_guard"]["action"] == "none"


async def test_boundary_guard_unavailable_does_nothing(monkeypatch):
    _stub_classify(monkeypatch, SafetyAssessment(available=False))
    ctx = await BoundaryGuardStage().process(_ctx("обычное сообщение про погоду"))
    assert ctx.early_response is None and ctx.safety_footer is None


async def test_boundary_guard_l0_urgent_skips_classifier(monkeypatch):
    called = {"n": 0}

    async def _fake(text, context=None):
        called["n"] += 1
        return SafetyAssessment(available=False)

    monkeypatch.setattr("app.llm.pipeline.stages.boundary_guard.safety_classifier.classify", _fake)
    ctx = await BoundaryGuardStage().process(_ctx("хочу покончить с собой"))
    assert ctx.early_response == CRISIS_RESPONSE          # L0 поймал
    assert called["n"] == 0                                # классификатор не звали


async def test_boundary_guard_data_entry_skips_classifier(monkeypatch):
    called = {"n": 0}

    async def _fake(text, context=None):
        called["n"] += 1
        return SafetyAssessment(available=False)

    monkeypatch.setattr("app.llm.pipeline.stages.boundary_guard.safety_classifier.classify", _fake)
    await BoundaryGuardStage().process(_ctx("давление 130 на 85"))
    assert called["n"] == 0


async def test_boundary_guard_disabled_flag_skips_classifier(monkeypatch):
    monkeypatch.setenv("LLM_SAFETY_LLM", "false")
    called = {"n": 0}

    async def _fake(text, context=None):
        called["n"] += 1
        return SafetyAssessment(available=False)

    monkeypatch.setattr("app.llm.pipeline.stages.boundary_guard.safety_classifier.classify", _fake)
    await BoundaryGuardStage().process(_ctx("обычное сообщение"))
    assert called["n"] == 0
