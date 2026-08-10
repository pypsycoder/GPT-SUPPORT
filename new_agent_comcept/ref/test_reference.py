"""
Тесты референсной реализации. Запуск: pytest test_reference.py -v

Здесь нет обращений к сети. Проверяется то, что ломается чаще всего:
  * стабильность префикса промпта (это деньги);
  * корректность JSON Schema для GigaChat;
  * инварианты tool-loop;
  * пороги memory gate.

Требует: pytest, pytest-asyncio, pydantic>=2.
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, Field

from gigachat_client import Usage, _parse_completion, _strip_fence, json_schema_for
from memory import FactCandidate, MemoryGate, POLICY_MIN_EVIDENCE
from prompt_assembly import PromptLayers, Turn, canonical_json, session_key, trim_window
from router import Intent, TOOLS_BY_INTENT, cosine, route_l0


# --------------------------------------------------------------------------- #
# Префикс промпта
# --------------------------------------------------------------------------- #

def _layers() -> PromptLayers:
    return PromptLayers(
        system="Ты — помощник поддержки пациента на гемодиализе.",
        profile="- response_style_preference: short_practical",
        summary="Обсуждали сон и усталость после сеансов.",
        window=[Turn("user", "привет"), Turn("assistant", "здравствуйте")],
        volatile=[Turn("user", "не могу уснуть")],
    )


def test_system_message_is_first_and_single():
    """GigaChat: 422, если system не первый или их больше одного."""
    msgs = _layers().build()
    assert msgs[0]["role"] == "system"
    assert sum(1 for m in msgs if m["role"] == "system") == 1


def test_prefix_survives_window_growth():
    """Рост диалога не должен трогать стабильную часть — иначе кэш обнуляется."""
    layers = _layers()
    before = layers.prefix_fingerprint()
    layers.window.append(Turn("user", "ещё вопрос"))
    layers.volatile = [Turn("user", "новая реплика")]
    assert layers.prefix_fingerprint() == before


def test_prefix_changes_on_profile_change():
    layers = _layers()
    before = layers.prefix_fingerprint()
    layers.profile += "\n- content_preference: practice_first"
    assert layers.prefix_fingerprint() != before


def test_session_key_includes_fingerprint():
    layers = _layers()
    key = session_key(7, "thread-1", layers.prefix_fingerprint())
    assert key.startswith("p7-thread-1-")


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_trim_window_starts_with_user():
    turns = []
    for i in range(10):
        turns.append(Turn("user", f"вопрос {i} " * 20))
        turns.append(Turn("assistant", f"ответ {i} " * 20))
    kept, evicted = trim_window(turns, max_turns=6, max_chars=500)
    assert kept[0].role == "user"
    assert len(kept) + len(evicted) == len(turns)
    assert evicted == turns[: len(evicted)]   # вытесняем только с головы


# --------------------------------------------------------------------------- #
# JSON Schema
# --------------------------------------------------------------------------- #

class Inner(BaseModel):
    level: str


class Outer(BaseModel):
    reply: str = Field(max_length=100)
    inner: Inner


def test_schema_has_no_refs():
    """$ref ломает strict-режим GigaChat. Схема должна быть плоской."""
    schema = json_schema_for(Outer)
    assert "$defs" not in schema
    assert "$ref" not in json.dumps(schema)
    assert schema["properties"]["inner"]["properties"]["level"]["type"] == "string"


def test_schema_has_required():
    """Без required модель вернёт произвольный JSON, даже при strict=true."""
    schema = json_schema_for(Outer)
    assert set(schema["required"]) == {"reply", "inner"}


# --------------------------------------------------------------------------- #
# Парсинг ответа
# --------------------------------------------------------------------------- #

def test_parse_usage_and_function_call():
    payload = {
        "choices": [{
            "message": {
                "content": "",
                "role": "assistant",
                "function_call": {"name": "get_recent_vitals", "arguments": {"days": 7}},
                "functions_state_id": "9b26f2cd-5efc-4005-a156-6914bdb89ad6",
            },
            "index": 0,
            "finish_reason": "function_call",
        }],
        "model": "GigaChat-2-Pro:2.0.28.2",
        "usage": {"prompt_tokens": 127, "completion_tokens": 46,
                  "total_tokens": 173, "precached_prompt_tokens": 500},
    }
    comp = _parse_completion(payload, 120)
    assert comp.function_call is not None
    assert comp.function_call.name == "get_recent_vitals"
    assert comp.functions_state_id
    assert comp.usage.precached_prompt_tokens == 500
    # 500 из 627 префикса пришли из кэша
    assert round(comp.usage.cache_hit_ratio, 2) == 0.8


def test_parse_function_arguments_as_string():
    """Аргументы могут прийти строкой — не должны терять форму."""
    payload = {
        "choices": [{
            "message": {"content": "", "role": "assistant",
                        "function_call": {"name": "f", "arguments": '{"days": 3}'}},
            "index": 0, "finish_reason": "function_call",
        }],
        "model": "GigaChat-2", "usage": {},
    }
    assert _parse_completion(payload, 1).function_call.arguments == {"days": 3}


def test_blacklist_detected():
    payload = {
        "choices": [{"message": {"content": "", "role": "assistant"},
                     "index": 0, "finish_reason": "blacklist"}],
        "model": "GigaChat-2", "usage": {},
    }
    assert _parse_completion(payload, 10).blocked is True


def test_strip_fence():
    assert _strip_fence('```json\n{"a":1}\n```') == '{"a":1}'
    assert _strip_fence('{"a":1}') == '{"a":1}'


def test_usage_add():
    total = Usage(10, 5, 100, 15) + Usage(20, 5, 0, 25)
    assert (total.prompt_tokens, total.total_tokens) == (30, 40)


# --------------------------------------------------------------------------- #
# Роутер
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text", [
    "не вижу смысла жить дальше",
    "не хочу больше жить",
    "хочу умереть",
    "думаю покончить с собой",
    "лучше бы я умер",
    "нет смысла продолжать лечиться",
    "больше не могу это выносить",
    "решил бросить диализ",
    "хочу отказаться от лечения",
    "хочу чтобы всё закончилось",
])
def test_l0_safety_recall(text):
    """
    Полнота важнее точности. Каждый пропуск здесь — реальный риск,
    поэтому набор расширяется из логов и НИКОГДА не сужается ради точности.
    """
    route = route_l0(text, "text")
    assert route is not None and route.intent == Intent.SAFETY


@pytest.mark.parametrize("text", [
    "мне как-то не по себе последние дни",
    "устал, но справляюсь",
    "расскажите про фосфор",
    "когда мой следующий сеанс",
    "плохо спал сегодня",
    "можно перенести сеанс",
])
def test_l0_safety_no_false_alarm_on_neutral(text):
    """Нейтральные фразы не должны эскалировать в кризис."""
    route = route_l0(text, "text")
    assert route is None or route.intent != Intent.SAFETY


@pytest.mark.parametrize("text", [
    "давление 190/110 и голова болит",
    "АД 200 на 100",          # пациенты часто пишут словом «на»
    "давление 185-95",
])
def test_l0_hypertensive_crisis(text):
    route = route_l0(text, "text")
    assert route is not None
    assert route.intent == Intent.CLINICAL
    assert route.model == "GigaChat-2-Max"


@pytest.mark.parametrize("text", [
    "давление 120/80, всё хорошо",
    "АД 130 на 85",
    "выпил 250 мл воды",       # регрессия: одиночное 3-значное число — не АД
    "вес 72 кг",
])
def test_l0_no_false_crisis_on_numbers(text):
    """
    В app/llm/router.py сейчас `\\b(\\d{3,})\\b` — любое трёхзначное число
    считается кризом, включая «250 мл». Здесь ловим пару чисел, а не любое.
    """
    assert route_l0(text, "text") is None


def test_l0_returns_none_when_unsure():
    """L0 не должен угадывать: непонятное уходит на L1."""
    assert route_l0("мне как-то не по себе последние дни", "text") is None


def test_l0_button_and_short():
    assert route_l0("", "button").intent == Intent.LOGISTICS
    assert route_l0("ок", "text").intent == Intent.SMALLTALK


def test_safety_gets_no_tools():
    """В кризисе не ходим в базы — отвечаем сразу."""
    assert TOOLS_BY_INTENT[Intent.SAFETY] == []


def test_every_intent_has_tools_and_model():
    """Новый интент без записи в таблицах уронит роутер в проде по KeyError."""
    from router import MODEL_BY_INTENT
    assert set(TOOLS_BY_INTENT) == set(Intent)
    assert set(MODEL_BY_INTENT) == set(Intent)


def test_every_intent_has_budget():
    from budget import BUDGET_BY_INTENT
    assert set(BUDGET_BY_INTENT) == set(Intent)


def test_routed_tools_are_registered():
    """Роутер не должен ссылаться на инструмент, которого нет в реестре."""
    from tools import registry
    referenced = {n for lst in TOOLS_BY_INTENT.values() for n in lst}
    assert [n for n in referenced if registry.get(n) is None] == []


def test_cosine():
    assert round(cosine([1, 0], [1, 0]), 3) == 1.0
    assert round(cosine([1, 0], [0, 1]), 3) == 0.0


# --------------------------------------------------------------------------- #
# Memory gate
# --------------------------------------------------------------------------- #

class _FakeStore:
    def __init__(self, existing: int = 0):
        self.existing = existing
        self.written: list[FactCandidate] = []

    async def count_pending_evidence(self, patient_id, key, value):
        return self.existing

    async def _upsert_fact(self, patient_id, cand):
        self.written.append(cand)


@pytest.mark.asyncio
async def test_gate_writes_explicit_preference_immediately():
    store = _FakeStore()
    gate = MemoryGate(store)  # type: ignore[arg-type]
    cand = FactCandidate(
        key="response_style_preference", value="short_practical",
        policy="explicit_user_preference",
        evidence="пиши покороче, пожалуйста", confidence=0.9,
    )
    [decision] = await gate.apply(1, [cand])
    assert decision.written is True


@pytest.mark.asyncio
async def test_gate_defers_repeated_pattern_until_threshold():
    store = _FakeStore(existing=0)
    gate = MemoryGate(store)  # type: ignore[arg-type]
    cand = FactCandidate(
        key="repeated_problem_pattern", value="insomnia_before_session",
        policy="repeated_pattern", evidence="снова не спал", confidence=0.8,
    )
    [d1] = await gate.apply(1, [cand])
    assert d1.written is False and "1_of_2" in d1.reason

    store.existing = 1
    [d2] = await gate.apply(1, [cand])
    assert d2.written is True


@pytest.mark.asyncio
async def test_gate_rejects_low_confidence():
    gate = MemoryGate(_FakeStore())  # type: ignore[arg-type]
    cand = FactCandidate(
        key="content_preference", value="video", policy="repeated_pattern",
        evidence="кажется, ему нравится видео", confidence=0.3,
    )
    [d] = await gate.apply(1, [cand])
    assert d.written is False and d.reason == "low_confidence"


def test_policy_thresholds_are_sane():
    assert POLICY_MIN_EVIDENCE["explicit_user_preference"] == 1
    assert POLICY_MIN_EVIDENCE["stable_behavior_signal"] >= 3


def test_fact_key_enum_is_closed():
    """Ключи — Literal, значит в JSON Schema уедут как enum и модель не изобретёт свой."""
    schema = json_schema_for(FactCandidate)
    assert "enum" in schema["properties"]["key"]


def test_fact_keys_and_ttl_are_in_sync():
    """Рассинхрон Literal и FACT_TTL даст KeyError при записи факта."""
    import typing
    from memory import ALLOWED_FACT_KEYS, FactKey
    assert set(typing.get_args(FactKey)) == set(ALLOWED_FACT_KEYS)
