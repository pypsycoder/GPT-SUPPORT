"""Тесты фазы инструментов в ``Agent.run()`` (шаг 7).

Паттерн стаба клиента — как в ``test_single_agent.py``, расширен методом
``call_with_functions``. ``messages`` — общий мутируемый список, поэтому
каждый вызов стаба сохраняет snapshot (копию), иначе все записи в истории
вызовов схлопнутся к финальному состоянию списка.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.llm import agent
from app.llm.agent.schemas import AgentReply
from app.llm.errors import LLMTransportError
from app.llm.pool import FunctionCall, FunctionCallResult, StructuredResult

pytestmark = [pytest.mark.unit]


def _reply_payload(**overrides) -> dict:
    payload = {
        "reply": "Вот что нашлось по теме.",
        "intent": "education",
        "technique_id": "нет",
        "safety_level": "none",
        "safety_kind": "none",
        "safety_reason": "нет",
        "next_action": "нет",
        "memory_candidates": [],
    }
    payload.update(overrides)
    return payload


class _StubToolClient:
    account_id = "A1-pro"

    def __init__(self, *, cwf_outcomes=(), structured_outcomes=()):
        self.cwf_outcomes = list(cwf_outcomes)
        self.structured_outcomes = list(structured_outcomes)
        self.cwf_calls: list[dict] = []
        self.structured_calls: list[dict] = []

    async def call_with_functions(self, messages, system_prompt, **kwargs):
        self.cwf_calls.append({"messages": [dict(m) for m in messages], "system": system_prompt, **kwargs})
        outcome = self.cwf_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def structured(self, messages, system_prompt, schema, **kwargs):
        self.structured_calls.append({"messages": [dict(m) for m in messages], "system": system_prompt, **kwargs})
        outcome = self.structured_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture()
def stub_tool_client(monkeypatch):
    holder: dict = {}

    def _install(*, cwf_outcomes=(), structured_outcomes=()):
        client = _StubToolClient(cwf_outcomes=cwf_outcomes, structured_outcomes=structured_outcomes)
        holder["client"] = client

        async def fake_get_available(model_tier, *, allow_fallback=False, sticky_key=None):
            return client

        monkeypatch.setattr(agent.loop.pool, "get_available", fake_get_available)
        return client

    holder["install"] = _install
    return holder


@pytest.mark.asyncio
async def test_no_allowed_tools_skips_tool_phase_entirely(stub_tool_client):
    """Regression: allowed_tools=None — поведение шага 4 не меняется."""
    client = stub_tool_client["install"](
        structured_outcomes=[StructuredResult(parsed=AgentReply.model_validate(_reply_payload()), raw_text="{}")]
    )
    layers = agent.build_layers(user_message="привет")

    run = await agent.Agent().run(layers, patient_id=7, thread_key="p7-default")

    assert run.ok
    assert run.hops == 0
    assert client.cwf_calls == []
    assert len(client.structured_calls) == 1


@pytest.mark.asyncio
async def test_one_tool_hop_appends_message_pair_before_structured_final(stub_tool_client, monkeypatch):
    fake_invoke = AsyncMock(return_value='{"hits": [{"title": "Урок", "snippet": "..."}]}')
    monkeypatch.setattr(agent.loop.tools.registry, "invoke", fake_invoke)

    client = stub_tool_client["install"](
        cwf_outcomes=[
            FunctionCallResult(
                content="",
                function_call=FunctionCall(name="search_education", arguments={"query": "диета"}),
                functions_state_id="fsid-1",
                finish_reason="function_call",
                tokens_in=50,
                tokens_out=10,
            ),
            FunctionCallResult(content="готов ответить", function_call=None, functions_state_id=None, finish_reason="stop"),
        ],
        structured_outcomes=[StructuredResult(parsed=AgentReply.model_validate(_reply_payload()), raw_text="{}")],
    )
    layers = agent.build_layers(user_message="можно мне картошку?")

    run = await agent.Agent().run(
        layers, patient_id=7, thread_key="p7-default", allowed_tools=["search_education"], db="the-db"
    )

    assert run.ok
    assert run.hops == 1
    assert len(client.cwf_calls) == 2

    fake_invoke.assert_awaited_once_with("search_education", {"query": "диета"}, patient_id=7, db="the-db")

    # Внутри фазы сбора (второй вызов call_with_functions) обмен с функцией
    # присутствует в нативном формате — оба сообщения, в правильном порядке.
    second_hop_messages = client.cwf_calls[1]["messages"]
    assistant_msg = next(m for m in second_hop_messages if m.get("function_call") is not None)
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == ""
    assert assistant_msg["function_call"] == {"name": "search_education", "arguments": {"query": "диета"}}
    assert assistant_msg["functions_state_id"] == "fsid-1"
    idx = second_hop_messages.index(assistant_msg)
    assert second_hop_messages[idx + 1]["role"] == "function"

    # Финальный structured() НЕ видит нативный function-обмен вообще (живым
    # прогоном пойман баг: response_format после role="function" ломает JSON
    # у GigaChat) — находки приходят обычной пользовательской репликой.
    final_messages = client.structured_calls[0]["messages"]
    assert not any(m.get("function_call") is not None for m in final_messages)
    assert not any(m.get("role") == "function" for m in final_messages)
    assert any("Урок" in m.get("content", "") for m in final_messages)


@pytest.mark.asyncio
async def test_max_hops_stops_the_loop_and_still_reaches_structured_final(stub_tool_client, monkeypatch):
    monkeypatch.setattr(
        agent.loop.tools.registry, "invoke", AsyncMock(return_value='{"hits": []}')
    )
    always_calls = lambda: FunctionCallResult(  # noqa: E731
        content="",
        function_call=FunctionCall(name="search_education", arguments={"query": "x"}),
        functions_state_id=None,
        finish_reason="function_call",
    )
    client = stub_tool_client["install"](
        cwf_outcomes=[always_calls() for _ in range(agent.loop.MAX_TOOL_HOPS)],
        structured_outcomes=[StructuredResult(parsed=AgentReply.model_validate(_reply_payload()), raw_text="{}")],
    )
    layers = agent.build_layers(user_message="что-то про диету")

    run = await agent.Agent().run(
        layers, patient_id=7, thread_key="p7-default", allowed_tools=["search_education"], db="the-db"
    )

    assert run.ok
    assert run.hops == agent.loop.MAX_TOOL_HOPS
    assert len(client.cwf_calls) == agent.loop.MAX_TOOL_HOPS


@pytest.mark.asyncio
async def test_tool_collection_llm_failure_falls_through_to_structured_final(stub_tool_client, monkeypatch):
    monkeypatch.setattr(agent.loop.tools.registry, "invoke", AsyncMock())
    client = stub_tool_client["install"](
        cwf_outcomes=[LLMTransportError("provider down")],
        structured_outcomes=[StructuredResult(parsed=AgentReply.model_validate(_reply_payload()), raw_text="{}")],
    )
    layers = agent.build_layers(user_message="привет")

    run = await agent.Agent().run(
        layers, patient_id=7, thread_key="p7-default", allowed_tools=["search_education"], db="the-db"
    )

    assert run.ok  # ход не падает целиком из-за сбоя на этапе сбора инструментами
    assert run.hops == 0
    agent.loop.tools.registry.invoke.assert_not_called()
