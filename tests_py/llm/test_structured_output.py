"""Тесты структурного вывода (response_format json_schema вместо парсеров)."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from app.llm import structured
from app.llm.agent.judge import JudgeVerdict
from app.llm.agent.schemas import AgentReply
from app.llm.errors import LLMResponseError
from app.llm.pool import GigaChatClient, StructuredResult, _SharedAccountState
from app.llm.router_l2 import RouterL2Reply


# Три разных по форме, реально используемых схемы — проверяем, что
# json_schema_for() ведёт себя одинаково на всех: разное число полей,
# разный state extra (ignore/forbid), с дефолтами и без.
ALL_SCHEMAS = (AgentReply, JudgeVerdict, RouterL2Reply)

# Схемы без единого дефолтного поля — на них естественно required == properties.
FULLY_REQUIRED_SCHEMAS = (JudgeVerdict, RouterL2Reply)


# --------------------------------------------------------------------------- #
# json_schema_for: три подводных камня из мануала
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("model", ALL_SCHEMAS, ids=lambda m: m.__name__)
def test_schema_is_flat_without_refs(model):
    """$ref ломает strict-режим — в схеме не должно остаться ни $ref, ни $defs."""
    blob = json.dumps(structured.json_schema_for(model), ensure_ascii=False)

    assert "$ref" not in blob
    assert "$defs" not in blob


@pytest.mark.parametrize("model", FULLY_REQUIRED_SCHEMAS, ids=lambda m: m.__name__)
def test_every_property_is_required(model):
    """Без required модель вернёт произвольный JSON даже при strict: true."""
    schema = structured.json_schema_for(model)

    structured.assert_required_present(schema)
    assert set(schema["required"]) == set(schema["properties"])


@pytest.mark.parametrize("model", ALL_SCHEMAS, ids=lambda m: m.__name__)
def test_schema_forbids_extra_properties(model):
    assert structured.json_schema_for(model)["additionalProperties"] is False


def test_assert_required_present_rejects_incomplete_schema():
    with pytest.raises(ValueError, match="without required fields"):
        structured.assert_required_present(
            {"properties": {"a": {}, "b": {}}, "required": ["a"]}
        )


def test_json_only_instruction_shared_across_every_structured_system_prompt():
    """Регрессия анализа шагов 1-4: формулировка была независимо продублирована
    (с расхождением) в agent/prompts.py, agent/judge.py и router_l2.py — теперь
    все ссылаются на один source of truth."""
    from app.llm.agent.judge import JUDGE_SYSTEM_PROMPT
    from app.llm.agent.prompts import AGENT_SYSTEM_PROMPT
    from app.llm.router_l2 import _SYSTEM_PROMPT as ROUTER_L2_SYSTEM_PROMPT

    assert structured.JSON_ONLY_INSTRUCTION in AGENT_SYSTEM_PROMPT
    assert structured.JSON_ONLY_INSTRUCTION in JUDGE_SYSTEM_PROMPT
    assert structured.JSON_ONLY_INSTRUCTION in ROUTER_L2_SYSTEM_PROMPT


def test_schema_drops_redundant_titles():
    schema = structured.json_schema_for(AgentReply)

    assert "title" not in schema
    assert all("title" not in prop for prop in schema["properties"].values())


def test_nested_model_gets_inlined():
    class Inner(BaseModel):
        value: str

    class Outer(BaseModel):
        inner: Inner

    schema = structured.json_schema_for(Outer)

    assert schema["properties"]["inner"]["properties"]["value"]["type"] == "string"
    assert "$defs" not in schema


def test_response_format_shape():
    rf = structured.response_format_for(AgentReply)

    assert rf["type"] == "json_schema"
    assert rf["strict"] is True
    assert "properties" in rf["schema"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ("```\n{}\n```", "{}"),
        ("  {}  ", "{}"),
        # Живым прогоном поймано (шаг 7): после function_call в истории GigaChat
        # иногда генерирует спецтокен вместо кавычки — валидный на вид JSON,
        # но `"` заменена буквальной строкой `<|superquote|>`.
        ("{<|superquote|>a<|superquote|>: 1}", '{"a": 1}'),
    ],
)
def test_strip_fence(raw, expected):
    assert structured.strip_fence(raw) == expected


# --------------------------------------------------------------------------- #
# Флаг
# --------------------------------------------------------------------------- #

def test_structured_disabled_by_default(monkeypatch):
    monkeypatch.delenv(structured.ENV_FLAG, raising=False)
    assert structured.structured_enabled() is False

    monkeypatch.setenv(structured.ENV_FLAG, "1")
    assert structured.structured_enabled() is True

    monkeypatch.setenv(structured.ENV_FLAG, "off")
    assert structured.structured_enabled() is False


# --------------------------------------------------------------------------- #
# GigaChatClient.structured()
# --------------------------------------------------------------------------- #

def _client() -> GigaChatClient:
    return GigaChatClient("A1", "key", "pro", shared_state=_SharedAccountState(api_key="key"))


def _agent_reply_payload(**overrides) -> dict:
    payload = {
        "reply": "Понимаю, это тяжело.",
        "intent": "emotional_support",
        "safety_level": "none",
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def recorded_calls(monkeypatch):
    calls: list[dict] = []
    replies: list[str] = []

    async def fake_call(self, messages, system_prompt, **kwargs):
        calls.append({"messages": messages, "system": system_prompt, **kwargs})
        return replies.pop(0), 10, 5, 20

    monkeypatch.setattr(GigaChatClient, "call", fake_call)
    return calls, replies


@pytest.mark.asyncio
async def test_structured_sends_response_format_and_parses(recorded_calls):
    calls, replies = recorded_calls
    replies.append(json.dumps(_agent_reply_payload(), ensure_ascii=False))

    result = await _client().structured(
        [{"role": "user", "content": "карточка"}],
        "system",
        AgentReply,
        step="agent",
    )

    assert isinstance(result, StructuredResult)
    assert result.repair_attempts == 0
    assert result.parsed.reply == "Понимаю, это тяжело."
    assert len(calls) == 1
    rf = calls[0]["response_format"]
    assert rf["type"] == "json_schema" and rf["strict"] is True
    # functions и response_format в одном запросе не смешиваем
    assert "functions" not in calls[0]
    # JSON дороже текста — потолок токенов поднят, иначе ответ обрежется
    assert calls[0]["max_tokens"] > 512


@pytest.mark.asyncio
async def test_structured_repairs_once_and_counts_it(recorded_calls):
    calls, replies = recorded_calls
    replies.append("совсем не JSON")
    replies.append(json.dumps(_agent_reply_payload(), ensure_ascii=False))

    result = await _client().structured(
        [{"role": "user", "content": "карточка"}],
        "system",
        AgentReply,
        step="agent",
    )

    assert result.repair_attempts == 1
    assert result.tokens_in == 20  # 10 + 10: расход обеих попыток
    assert len(calls) == 2
    # Repair виден в телеметрии отдельным шагом — по нему считается доля починок
    assert calls[1]["step"] == "agent_repair"
    # Починка дописывается в хвост: префикс не трогаем
    assert calls[1]["messages"][0] == calls[0]["messages"][0]
    assert calls[1]["messages"][-1]["role"] == "user"


@pytest.mark.asyncio
async def test_structured_raises_after_second_failure(recorded_calls):
    calls, replies = recorded_calls
    replies.extend(["не JSON", "тоже не JSON"])

    with pytest.raises(LLMResponseError, match="twice"):
        await _client().structured(
            [{"role": "user", "content": "карточка"}],
            "system",
            AgentReply,
        )


@pytest.mark.asyncio
async def test_structured_without_repair_raises_immediately(recorded_calls):
    calls, replies = recorded_calls
    replies.append("не JSON")

    with pytest.raises(LLMResponseError):
        await _client().structured(
            [{"role": "user", "content": "карточка"}],
            "system",
            AgentReply,
            repair=False,
        )

    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# Фикс 1: lite не держит схему — откат на текстовые карточки
# --------------------------------------------------------------------------- #

def test_structured_disabled_for_lite_tier(monkeypatch):
    monkeypatch.setenv(structured.ENV_FLAG, "1")

    assert structured.structured_enabled_for_tier("lite") is False
    assert structured.structured_enabled_for_tier("LITE") is False
    assert structured.structured_enabled_for_tier("pro") is True
    assert structured.structured_enabled_for_tier("max") is True


def test_structured_tier_check_respects_the_flag(monkeypatch):
    monkeypatch.delenv(structured.ENV_FLAG, raising=False)

    assert structured.structured_enabled_for_tier("pro") is False
