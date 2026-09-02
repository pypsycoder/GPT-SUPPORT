"""Сквозной тест пайплайна: реальные 5 стадий, GigaChat замокан на уровне пула.

Единственная сетевая точка пайплайна — `SupervisorStage` через
`agent.Agent().run()` → `pool.get_available()`. Мокаем её; всё остальное
(boundary_guard, classification, data_entry, memory_write) работает по-настоящему.
`db=None` — стадии сами пропускают работу с БД.
"""

from __future__ import annotations

import pytest

from app.llm import agent
from app.llm.agent.schemas import AgentReply
from app.llm.errors import LLMResponseError
from app.llm.pipeline import LLMPipeline, LLMRequest
from app.llm.pool import FunctionCallResult, StructuredResult
from app.llm.router import ModelTier, RequestType, RouterResult
from app.llm.safety_classifier import SafetyAssessment


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


def _card(**overrides) -> AgentReply:
    payload = {
        "reply": "Понимаю, это непросто. Давай разберёмся вместе.",
        "intent": "emotional_support",
        "technique_id": "нет",
        "safety_level": "none",
        "safety_kind": "none",
        "safety_reason": "нет",
        "next_action": "нет",
        "memory_candidates": [],
    }
    payload.update(overrides)
    return AgentReply.model_validate(payload)


class _StubClient:
    account_id = "A1-pro"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.structured_calls = 0

    async def call_with_functions(self, messages, system_prompt, **kwargs):
        # инструмент не зовём — сразу к структурному ответу
        return FunctionCallResult(
            content="", function_call=None, functions_state_id=None, finish_reason="stop"
        )

    async def structured(self, messages, system_prompt, schema, **kwargs):
        self.structured_calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture()
def stub_llm(monkeypatch):
    holder: dict = {}

    def _install(*outcomes, safety=None):
        client = _StubClient(outcomes)
        holder["client"] = client

        async def _fake_get_available(model_tier, *, allow_fallback=False, sticky_key=None):
            return client

        monkeypatch.setattr(agent.loop.pool, "get_available", _fake_get_available)

        # 2-й эшелон safety (boundary_guard → safety_classifier.classify) — свой
        # мок, чтобы не тратить outcome агента и не считаться в structured_calls.
        result = safety or SafetyAssessment(level="none", subject="self", available=True)

        async def _fake_safety(text, context=None):
            return result

        monkeypatch.setattr("app.llm.pipeline.stages.boundary_guard.safety_classifier.classify", _fake_safety)
        return client

    return _install


def _ok_result(card: AgentReply) -> StructuredResult:
    return StructuredResult(parsed=card, raw_text="{}", tokens_in=700, tokens_out=90, latency_ms=800)


async def _run(user_input: str, *, router_result=None) -> tuple:
    resp = await LLMPipeline().process(
        LLMRequest(patient_id=999001, user_input=user_input, source="text",
                   router_result=router_result, db=None)
    )
    stages = [s["name"] for s in resp.diagnostics.get("stages", [])]
    return resp, stages


# --------------------------------------------------------------------------- #
# Ранние ответы — модель не зовётся
# --------------------------------------------------------------------------- #

async def test_crisis_short_circuits_at_boundary_guard(stub_llm):
    client = stub_llm(_ok_result(_card()))

    resp, stages = await _run("не хочу больше жить")

    assert stages == ["boundary_guard"]
    assert client.structured_calls == 0
    assert "8-800-2000-122" in resp.response or "телефон доверия" in resp.response.lower()
    assert resp.account_id.startswith("BOUNDARY_GUARD")


async def test_medical_urgent_short_circuits_with_the_medical_protocol(stub_llm):
    client = stub_llm(_ok_result(_card()))

    resp, stages = await _run("у меня пошла кровь из фистулы")

    assert stages == ["boundary_guard"]
    assert client.structured_calls == 0
    assert resp.account_id == "BOUNDARY_GUARD_MEDICAL_URGENT"


async def test_bp_reading_short_circuits_at_data_entry(stub_llm):
    client = stub_llm(_ok_result(_card()))

    resp, stages = await _run("давление 125 на 85")

    assert stages == ["boundary_guard", "classification", "data_entry"]
    assert client.structured_calls == 0
    assert "Записал" in resp.response
    assert resp.pending_vitals == [{"type": "BP", "systolic": 125, "diastolic": 85}]


async def test_sleep_report_short_circuits_with_a_tracker_button(stub_llm):
    client = stub_llm(_ok_result(_card()))

    resp, stages = await _run("спал 4 часа сегодня")

    assert stages == ["boundary_guard", "classification", "data_entry"]
    assert client.structured_calls == 0
    assert resp.buttons == [{"label": "Внести данные о сне", "action": "open_sleep"}]


async def test_routine_report_short_circuits_with_a_tracker_button(stub_llm):
    client = stub_llm(_ok_result(_card()))

    resp, stages = await _run("сегодня соблюдал распорядок дня")

    assert stages == ["boundary_guard", "classification", "data_entry"]
    assert client.structured_calls == 0
    assert resp.buttons == [{"label": "Открыть распорядок дня", "action": "open_schedule"}]


# --------------------------------------------------------------------------- #
# Полный проход — модель зовётся один раз
# --------------------------------------------------------------------------- #

async def test_normal_message_runs_all_five_stages_and_calls_the_model_once(stub_llm):
    client = stub_llm(_ok_result(_card(reply="Слышу тебя. Что сейчас тяжелее всего?")))

    resp, stages = await _run(
        "последние дни всё валится из рук, ничего не радует",
        router_result=RouterResult(RequestType.EMOTIONAL, ModelTier.PRO, "emotion", 2),
    )

    assert stages == ["boundary_guard", "classification", "data_entry", "supervisor", "memory_write"]
    assert client.structured_calls == 1
    assert resp.response == "Слышу тебя. Что сейчас тяжелее всего?"
    assert resp.tokens_input == 700 and resp.tokens_output == 90
    assert resp.supervisor_state is not None


async def test_safety_llm_passive_ideation_appends_soft_footer(stub_llm):
    from app.llm.safety_responses import SAFETY_FOOTER_PASSIVE

    stub_llm(
        _ok_result(_card(reply="Слышу, как тебе тяжело. Расскажи, что сейчас происходит?")),
        safety=SafetyAssessment(level="ideation_passive", subject="self", available=True),
    )

    resp, stages = await _run(
        "устал бороться, зачем вообще продолжать все эти процедуры",
        router_result=RouterResult(RequestType.EMOTIONAL, ModelTier.PRO, "emotion", 2),
    )

    assert stages[-1] == "memory_write"
    assert resp.response.startswith("Слышу, как тебе тяжело.")
    assert resp.response.rstrip().endswith(SAFETY_FOOTER_PASSIVE.strip())
    bg = resp.diagnostics["boundary_guard"]
    assert bg["type"] == "safety_llm" and bg["action"] == "footer"


async def test_safety_llm_plan_short_circuits_before_generation(stub_llm):
    client = stub_llm(
        _ok_result(_card()),
        safety=SafetyAssessment(level="plan_or_imminent", subject="self", available=True),
    )

    resp, stages = await _run(
        "решил уже. на выходных, когда дома никого не будет",
        router_result=RouterResult(RequestType.EMOTIONAL, ModelTier.PRO, "emotion", 2),
    )

    assert stages == ["boundary_guard"]
    assert client.structured_calls == 0
    assert "8-800-2000-122" in resp.response
    assert resp.account_id == "BOUNDARY_GUARD_SAFETY_LLM"


async def test_safety_footer_not_doubled_when_agent_self_escalates(stub_llm):
    """classifier дал passive (плашка), но агент сам поднял urgent → ответ
    перекрыт кризис-протоколом, плашка НЕ дописывается (в тексте уже есть номер)."""
    stub_llm(
        _ok_result(_card(
            reply="держись", safety_level="urgent", safety_kind="psychological",
            safety_reason="прямая речь о нежелании жить",
        )),
        safety=SafetyAssessment(level="ideation_passive", subject="self", available=True),
    )
    resp, _ = await _run(
        "не вижу смысла продолжать всё это",
        router_result=RouterResult(RequestType.EMOTIONAL, ModelTier.PRO, "emotion", 2),
    )
    assert resp.response.count("8-800-2000-122") == 1     # ровно один телефон, не два
    assert "держись" not in resp.response


async def test_safety_llm_distress_sets_hint_no_footer(stub_llm):
    """distress от классификатора: подсказка агенту (concern), плашки нет."""
    stub_llm(
        _ok_result(_card(reply="Слышу тебя.")),
        safety=SafetyAssessment(level="distress", subject="self", available=True),
    )
    resp, stages = await _run(
        "руки опускаются, ничего не хочу",
        router_result=RouterResult(RequestType.EMOTIONAL, ModelTier.PRO, "emotion", 2),
    )
    assert stages[-1] == "memory_write"
    assert resp.diagnostics["boundary_guard"]["action"] == "hint"
    assert "8-800-2000-122" not in resp.response       # плашки нет
    assert resp.response == "Слышу тебя."


async def test_agent_urgent_verdict_is_overridden_by_the_safety_net(stub_llm):
    stub_llm(_ok_result(_card(
        reply="держись, всё наладится",
        safety_level="urgent", safety_kind="psychological",
        safety_reason="пациент прямо говорит о нежелании жить",
    )))

    resp, stages = await _run(
        "мне так тяжело, я не вижу выхода",
        router_result=RouterResult(RequestType.EMOTIONAL, ModelTier.PRO, "emotion", 2),
    )

    assert stages[-1] == "memory_write"
    # текст агента выброшен, подставлен кризисный протокол
    assert "держись, всё наладится" not in resp.response
    assert "8-800-2000-122" in resp.response
    net = resp.diagnostics["supervisor"]["safety_net"]
    assert net["reply_overridden"] is True


async def test_agent_schema_failure_falls_back_to_a_technical_reply(stub_llm):
    stub_llm(
        LLMResponseError("schema validation failed twice"),
        LLMResponseError("schema validation failed twice"),
    )

    resp, stages = await _run(
        "расскажи про диету",
        router_result=RouterResult(RequestType.EMOTIONAL, ModelTier.PRO, "education", 2),
    )

    assert stages == ["boundary_guard", "classification", "data_entry", "supervisor", "memory_write"]
    assert "техническая заминка" in resp.response
    assert resp.diagnostics["supervisor"]["execution_kind"] == "агент_ошибка"
