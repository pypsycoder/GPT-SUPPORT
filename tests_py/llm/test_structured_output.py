"""Тесты структурного вывода (шаг 3: response_format json_schema вместо парсеров)."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ValidationError

from app.llm import structured
from app.llm.errors import LLMResponseError
from app.llm.langgraph_supervisor import policy, schemas
from app.llm.langgraph_supervisor.models import FirstModuleState
from app.llm.pool import GigaChatClient, StructuredResult, _SharedAccountState
from app.llm.supervisor.models import CurrentState


ALL_SCHEMAS = (
    schemas.IntakeCardSchema,
    schemas.DelegationCardSchema,
    schemas.EmotionalExpertCardSchema,
    schemas.EducationExpertCardSchema,
)


# --------------------------------------------------------------------------- #
# json_schema_for: три подводных камня из мануала
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("model", ALL_SCHEMAS, ids=lambda m: m.__name__)
def test_schema_is_flat_without_refs(model):
    """$ref ломает strict-режим — в схеме не должно остаться ни $ref, ни $defs."""
    blob = json.dumps(structured.json_schema_for(model), ensure_ascii=False)

    assert "$ref" not in blob
    assert "$defs" not in blob


@pytest.mark.parametrize("model", ALL_SCHEMAS, ids=lambda m: m.__name__)
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


def test_schema_drops_redundant_titles():
    schema = structured.json_schema_for(schemas.DelegationCardSchema)

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
    rf = structured.response_format_for(schemas.IntakeCardSchema)

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
# Схемы карточек: русские алиасы = ключи, понятные существующим parse_*_card
# --------------------------------------------------------------------------- #

def test_intake_schema_uses_russian_aliases():
    keys = set(structured.json_schema_for(schemas.IntakeCardSchema)["properties"])

    assert keys == {
        "Проблема",
        "Контекст",
        "Готово к передаче",
        "Нужно уточнение",
        "Вопрос",
        "Обоснование",
    }


def test_emotional_schema_has_all_eleven_fields():
    keys = list(structured.json_schema_for(schemas.EmotionalExpertCardSchema)["properties"])

    assert keys == [
        "Поддержка",
        "Оценка",
        "Стратегия",
        "Режим",
        "Шаг сейчас",
        "Вопрос пациенту",
        "Ветка",
        "Тип ветки",
        "Возврат к протоколу",
        "План на следующий ход",
        "Обоснование",
    ]


def test_literal_fields_become_enums():
    props = structured.json_schema_for(schemas.EmotionalExpertCardSchema)["properties"]

    assert props["Режим"]["enum"] == ["уточнить", "интервенция"]
    assert props["Оценка"]["enum"] == ["хорошо", "частично", "не_помогло", "нет_данных"]


def test_schema_rejects_value_outside_literal():
    with pytest.raises(ValidationError):
        schemas.EmotionalExpertCardSchema.model_validate(
            {
                "Поддержка": "ок",
                "Оценка": "отлично",  # нет в перечислении
                "Стратегия": "продолжить",
                "Режим": "интервенция",
                "Шаг сейчас": "[p01] сделай вдох",
                "Вопрос пациенту": "нет",
                "Ветка": "нет",
                "Тип ветки": "нет",
                "Возврат к протоколу": "нет",
                "План на следующий ход": "продолжить технику",
                "Обоснование": "нужна интервенция",
            }
        )


def _emotional_payload() -> dict[str, str]:
    return {
        "Поддержка": "Это правда тяжело",
        "Оценка": "нет_данных",
        "Стратегия": "продолжить",
        "Режим": "интервенция",
        "Шаг сейчас": "[p01] сделай медленный выдох — это снизит напряжение",
        "Вопрос пациенту": "нет",
        "Ветка": "нет",
        "Тип ветки": "нет",
        "Возврат к протоколу": "нет",
        "План на следующий ход": "оценить эффект техники",
        "Обоснование": "техника снизит возбуждение",
    }


def test_fields_from_model_feeds_existing_parser():
    """Мост в существующие parse_*_card: те же русские ключи, что у текстовой карточки."""
    card_schema = schemas.EmotionalExpertCardSchema.model_validate(_emotional_payload())

    fields = schemas.fields_from_model(card_schema)
    card = policy.parse_emotional_expert_card(fields)

    assert card.support == "Это правда тяжело"
    assert card.step_now.startswith("[p01]")
    assert card.follow_up == "нет"


def test_business_validation_still_applies_to_structured_output():
    """Схема гарантирует состав полей, но не бизнес-правила — они остаются в validate_*."""
    payload = _emotional_payload()
    payload["Вопрос пациенту"] = "Что чувствуешь сейчас?"  # шаг И вопрос одновременно

    fields = schemas.fields_from_model(schemas.EmotionalExpertCardSchema.model_validate(payload))

    with pytest.raises(ValueError, match="choose one"):
        policy.parse_emotional_expert_card(fields)


# --------------------------------------------------------------------------- #
# Флаг и формат-блоки системных промптов
# --------------------------------------------------------------------------- #

def test_structured_disabled_by_default(monkeypatch):
    monkeypatch.delenv(structured.ENV_FLAG, raising=False)
    assert structured.structured_enabled() is False

    monkeypatch.setenv(structured.ENV_FLAG, "1")
    assert structured.structured_enabled() is True

    monkeypatch.setenv(structured.ENV_FLAG, "off")
    assert structured.structured_enabled() is False


@pytest.mark.parametrize(
    "build_prompt",
    [
        policy.build_intake_system_prompt,
        policy.build_delegation_system_prompt,
        policy.build_emotional_expert_system_prompt,
        policy.build_education_expert_system_prompt,
    ],
)
def test_system_prompt_switches_format_block(monkeypatch, build_prompt):
    monkeypatch.delenv(structured.ENV_FLAG, raising=False)
    legacy = build_prompt()

    monkeypatch.setenv(structured.ENV_FLAG, "1")
    json_mode = build_prompt()

    assert "JSON-объект строго по переданной схеме" in json_mode
    assert "JSON-объект строго по переданной схеме" not in legacy
    assert "одно поле в строке" not in json_mode


def test_structured_prompt_keeps_domain_rules(monkeypatch):
    """Меняется только транспорт: правила поведения остаются те же."""
    monkeypatch.setenv(structured.ENV_FLAG, "1")
    prompt = policy.build_intake_system_prompt()

    assert "причина пользователю не известна" in prompt
    assert "clarification_streak >= 2" in prompt
    assert "education_grounding_available" in prompt


# --------------------------------------------------------------------------- #
# GigaChatClient.structured()
# --------------------------------------------------------------------------- #

def _client() -> GigaChatClient:
    return GigaChatClient("A1", "key", "pro", shared_state=_SharedAccountState(api_key="key"))


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
    replies.append(json.dumps(_emotional_payload(), ensure_ascii=False))

    result = await _client().structured(
        [{"role": "user", "content": "карточка"}],
        "system",
        schemas.EmotionalExpertCardSchema,
        step="supervisor",
    )

    assert isinstance(result, StructuredResult)
    assert result.repair_attempts == 0
    assert result.parsed.support == "Это правда тяжело"
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
    replies.append(json.dumps(_emotional_payload(), ensure_ascii=False))

    result = await _client().structured(
        [{"role": "user", "content": "карточка"}],
        "system",
        schemas.EmotionalExpertCardSchema,
        step="supervisor",
    )

    assert result.repair_attempts == 1
    assert result.tokens_in == 20  # 10 + 10: расход обеих попыток
    assert len(calls) == 2
    # Repair виден в телеметрии отдельным шагом — по нему считается доля починок
    assert calls[1]["step"] == "supervisor_repair"
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
            schemas.EmotionalExpertCardSchema,
        )


@pytest.mark.asyncio
async def test_structured_without_repair_raises_immediately(recorded_calls):
    calls, replies = recorded_calls
    replies.append("не JSON")

    with pytest.raises(LLMResponseError):
        await _client().structured(
            [{"role": "user", "content": "карточка"}],
            "system",
            schemas.EmotionalExpertCardSchema,
            repair=False,
        )

    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# policy._call_structured_llm: обе ветки
# --------------------------------------------------------------------------- #

def _state() -> FirstModuleState:
    state = FirstModuleState(
        user_message="мне тревожно",
        current_state=CurrentState(),
        message_type="full_message",
        model_tier="pro",
    )
    state.session_id = "p7-default"
    state.patient_id = 7
    return state


@pytest.fixture()
def stub_pool(monkeypatch):
    holder: dict = {"calls": [], "structured_calls": [], "reply": "", "parsed": None}

    class _Stub:
        account_id = "A1"

        async def call(self, messages, system_prompt, **kwargs):
            holder["calls"].append({"messages": messages, "system": system_prompt, **kwargs})
            return holder["reply"], 10, 5, 20

        async def structured(self, messages, system_prompt, schema, **kwargs):
            holder["structured_calls"].append({"schema": schema, **kwargs})
            return StructuredResult(
                parsed=schema.model_validate(holder["parsed"]),
                raw_text=json.dumps(holder["parsed"], ensure_ascii=False),
                tokens_in=10,
                tokens_out=5,
                latency_ms=20,
            )

    async def fake_get_available(model_tier, *, allow_fallback=False, sticky_key=None):
        return _Stub()

    monkeypatch.setattr(policy.pool, "get_available", fake_get_available)
    return holder


@pytest.mark.asyncio
async def test_call_uses_field_block_when_flag_off(monkeypatch, stub_pool):
    monkeypatch.delenv(structured.ENV_FLAG, raising=False)
    stub_pool["reply"] = "Эксперт: education\nЗадача: объяснить\nОбоснование: нужен эксперт"

    result = await policy._call_structured_llm(
        system_prompt="system",
        user_prompt="user",
        model_tier="pro",
        strict_model_tier=False,
        temperature=0.1,
        session_id="p7-default",
        state=_state(),
        schema=schemas.DelegationCardSchema,
    )

    assert result.parse_mode == "field_block"
    assert result.fields is None
    assert stub_pool["structured_calls"] == []
    fields = policy._fields_from_result(result, {"Эксперт", "Задача", "Обоснование"})
    assert fields["Эксперт"] == "education"


@pytest.mark.asyncio
async def test_call_uses_structured_when_flag_on(monkeypatch, stub_pool):
    monkeypatch.setenv(structured.ENV_FLAG, "1")
    stub_pool["parsed"] = {
        "Эксперт": "education",
        "Задача": "объяснить",
        "Обоснование": "нужен эксперт",
    }

    result = await policy._call_structured_llm(
        system_prompt="system",
        user_prompt="user",
        model_tier="pro",
        strict_model_tier=False,
        temperature=0.1,
        session_id="p7-default",
        state=_state(),
        schema=schemas.DelegationCardSchema,
    )

    assert result.parse_mode == "structured"
    assert stub_pool["calls"] == []
    assert stub_pool["structured_calls"][0]["schema"] is schemas.DelegationCardSchema
    assert stub_pool["structured_calls"][0]["patient_id"] == 7
    fields = policy._fields_from_result(result, set())
    assert fields == stub_pool["parsed"]


@pytest.mark.asyncio
async def test_structured_failure_becomes_parse_error(monkeypatch):
    monkeypatch.setenv(structured.ENV_FLAG, "1")

    class _Stub:
        account_id = "A1"

        async def structured(self, *args, **kwargs):
            raise LLMResponseError("schema validation failed twice: boom")

    async def fake_get_available(model_tier, *, allow_fallback=False, sticky_key=None):
        return _Stub()

    monkeypatch.setattr(policy.pool, "get_available", fake_get_available)

    result = await policy._call_structured_llm(
        system_prompt="system",
        user_prompt="user",
        model_tier="pro",
        strict_model_tier=False,
        temperature=0.1,
        session_id="p7-default",
        state=_state(),
        schema=schemas.DelegationCardSchema,
    )

    assert result.parse_mode == "structured"
    assert result.repair_attempts == 1
    with pytest.raises(ValueError, match="boom"):
        policy._fields_from_result(result, set())


@pytest.mark.asyncio
async def test_extract_delegation_card_end_to_end_structured(monkeypatch, stub_pool):
    monkeypatch.setenv(structured.ENV_FLAG, "1")
    stub_pool["parsed"] = {
        "Эксперт": "эмоциональная_поддержка",
        "Задача": "поддержать при тревоге",
        "Обоснование": "нужна поддержка состояния",
    }
    state = _state()
    state.intake_card = None

    card, diagnostics = await policy.extract_delegation_card(state)

    assert card is not None
    assert card.task == "поддержать при тревоге"
    assert diagnostics["parse_mode"] == "structured"
    assert diagnostics["repair_attempts"] == 0
    assert diagnostics["succeeded_on_attempt"] == 1


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


@pytest.mark.parametrize(
    "build_prompt",
    [
        policy.build_intake_system_prompt,
        policy.build_delegation_system_prompt,
        policy.build_emotional_expert_system_prompt,
        policy.build_education_expert_system_prompt,
    ],
)
def test_lite_prompt_keeps_text_card_format(monkeypatch, build_prompt):
    """Формат промпта обязан совпадать с тем, как мы будем парсить ответ."""
    monkeypatch.setenv(structured.ENV_FLAG, "1")

    assert "JSON-объект строго по переданной схеме" not in build_prompt(model_tier="lite")
    assert "JSON-объект строго по переданной схеме" in build_prompt(model_tier="pro")


@pytest.mark.asyncio
async def test_call_falls_back_to_text_on_lite(monkeypatch, stub_pool):
    monkeypatch.setenv(structured.ENV_FLAG, "1")
    stub_pool["reply"] = "Эксперт: education\nЗадача: объяснить\nОбоснование: нужен эксперт"

    result = await policy._call_structured_llm(
        system_prompt="system",
        user_prompt="user",
        model_tier="lite",
        strict_model_tier=False,
        temperature=0.1,
        session_id="p7-default",
        state=_state(),
        schema=schemas.DelegationCardSchema,
    )

    assert result.parse_mode == "field_block"
    assert stub_pool["structured_calls"] == []


# --------------------------------------------------------------------------- #
# Фикс 2: модель дублирует имя поля внутрь значения
# --------------------------------------------------------------------------- #

def test_echoed_field_label_is_stripped_from_value():
    payload = _emotional_payload()
    payload["Поддержка"] = "Поддержка: -"

    fields = schemas.fields_from_model(schemas.EmotionalExpertCardSchema.model_validate(payload))

    assert fields["Поддержка"] == "-"


def test_value_that_merely_contains_colon_is_untouched():
    payload = _emotional_payload()
    payload["Шаг сейчас"] = "[p01] сделай вдох: медленно, на счёт четыре"

    fields = schemas.fields_from_model(schemas.EmotionalExpertCardSchema.model_validate(payload))

    assert fields["Шаг сейчас"] == "[p01] сделай вдох: медленно, на счёт четыре"


@pytest.mark.parametrize("dash", ["-", "—", "–", "—.", "-.", " - ", "нет"])
def test_dash_support_never_reaches_the_patient(dash):
    payload = _emotional_payload()
    payload["Поддержка"] = dash

    card = policy.parse_emotional_expert_card(
        schemas.fields_from_model(schemas.EmotionalExpertCardSchema.model_validate(payload))
    )
    reply = policy.build_emotional_reply(card)

    assert not reply.startswith(dash.strip())
    assert reply.startswith("сделай медленный выдох")


def test_real_support_still_reaches_the_patient():
    card = policy.parse_emotional_expert_card(
        schemas.fields_from_model(schemas.EmotionalExpertCardSchema.model_validate(_emotional_payload()))
    )

    assert policy.build_emotional_reply(card).startswith("Это правда тяжело")
