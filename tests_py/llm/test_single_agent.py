"""Тесты одноагентной ветки (шаг 4)."""

from __future__ import annotations

import json

import pytest

from app.llm import agent, prompt_assembly, structured
from app.llm.agent.judge import JudgeVerdict
from app.llm.agent.schemas import AgentReply
from app.llm.errors import LLMResponseError
from app.llm.pipeline.stages import supervisor as supervisor_stage
from app.llm.pipeline.types import LLMRequest, PipelineContext
from app.llm.pool import FunctionCallResult, StructuredResult
from app.llm.router import ModelTier, RequestType, RouterResult


def _reply_payload(**overrides) -> dict:
    payload = {
        "reply": "Понимаю, это тяжело. Давай попробуем короткое дыхательное упражнение.",
        "intent": "emotional_support",
        "technique_id": "нет",
        "safety_level": "none",
        "safety_kind": "none",
        "safety_reason": "нет",
        "next_action": "предложить практику дыхания",
        "memory_candidates": [],
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# Схема
# --------------------------------------------------------------------------- #

def test_agent_schema_is_flat():
    """$ref ломает strict-режим — схема должна остаться плоской."""
    blob = json.dumps(structured.json_schema_for(AgentReply), ensure_ascii=False)

    assert "$ref" not in blob and "$defs" not in blob


def test_only_the_three_irreplaceable_fields_are_required():
    """Обязательных ровно три.

    Раньше обязательными были все восемь — по документации GigaChat, где сказано,
    что без required модель возвращает произвольный JSON. На живом прогоне вышло
    наоборот: на «привет» и «спасибо» модель обрывала карточку, валидация падала
    целиком, и 4 из 5 коротких реплик уходили на откат к старой ветке.
    Остальным полям дали дефолты — потеря поля дешевле потери всей карточки.
    """
    schema = structured.json_schema_for(AgentReply)

    assert set(schema["required"]) == {"reply", "intent", "safety_level"}


def test_minimal_card_from_the_model_is_accepted():
    card = AgentReply.model_validate(
        {"reply": "Привет!", "intent": "smalltalk", "safety_level": "none"}
    )

    assert card.technique_id == "нет"
    assert card.safety_kind == "none"
    assert card.memory_candidates == []


def test_truncated_key_does_not_kill_the_card():
    """Модель присылала safekind вместо safety_kind — лишний ключ игнорируем."""
    card = AgentReply.model_validate(
        {"reply": "ок", "intent": "smalltalk", "safety_level": "none", "safekind": "none"}
    )

    assert card.reply == "ок"


def test_empty_safety_kind_means_no_risk():
    """При отсутствии риска GigaChat присылает пустую строку вместо none."""
    card = AgentReply.model_validate(
        {"reply": "ок", "intent": "smalltalk", "safety_level": "none", "safety_kind": ""}
    )

    assert card.safety_kind == "none"


def test_null_safety_reason_and_next_action_fall_back_to_default():
    """Живым прогоном (16-ходовый тред, cross-cutting проверка свёртки
    истории): GigaChat прислал safety_reason: null, next_action: null —
    оба поля типа str, None не проходил валидацию."""
    card = AgentReply.model_validate(
        {
            "reply": "ок",
            "intent": "emotional_support",
            "safety_level": "none",
            "technique_id": None,
            "safety_reason": None,
            "next_action": None,
        }
    )

    assert card.technique_id == "нет"
    assert card.safety_reason == "нет"
    assert card.next_action == "нет"


def test_free_text_safety_kind_falls_back_to_none():
    """Живым прогоном (LLM_test/reports/2026.08.24_23.00, single_agent,
    thread phase1-3to6): на concern модель прислала safety_kind: "бессонница"
    вместо enum-значения — валидация падала дважды подряд с одной ошибкой."""
    card = AgentReply.model_validate(
        {
            "reply": "ок",
            "intent": "emotional_support",
            "safety_level": "concern",
            "safety_kind": "бессонница",
        }
    )

    assert card.safety_kind == "none"


def test_empty_memory_candidates_means_no_candidates():
    """Живым прогоном (фаза 1, LLM_test/reports/2026.08.24_21.59.md, ходы 1/6/7):
    GigaChat присылает memory_candidates: "" вместо [] — так же, как safety_kind
    выше — и это ронял single_agent на откат к старой ветке."""
    card = AgentReply.model_validate(
        {"reply": "ок", "intent": "smalltalk", "safety_level": "none", "memory_candidates": ""}
    )

    assert card.memory_candidates == []


def test_agent_schema_carries_routing_fields():
    """Ради этого и берётся схема: маршрутные поля приходят вместе с текстом."""
    props = structured.json_schema_for(AgentReply)["properties"]

    assert props["safety_level"]["enum"] == ["none", "concern", "urgent"]
    assert props["intent"]["enum"] == [
        "emotional_support",
        "education",
        "smalltalk",
        "safety",
    ]





# --------------------------------------------------------------------------- #
# Слои промпта
# --------------------------------------------------------------------------- #

def test_agent_uses_one_stable_system_prompt():
    """Смысл шага 4: один системный промпт на ход вместо трёх разных."""
    first = agent.build_layers(user_message="привет")
    second = agent.build_layers(user_message="совсем другое сообщение", rag_fragments=["фрагмент"])

    assert first.system == second.system
    assert first.prefix_fingerprint() == second.prefix_fingerprint()


def test_agent_window_growth_does_not_move_the_prefix():
    history: list[dict[str, str]] = []
    fingerprints = set()
    for index in range(5):
        layers = agent.build_layers(
            user_message=f"ход {index}", profile_block="Данные пациента:\nСон: среднее 6ч", history=list(history)
        )
        fingerprints.add(layers.prefix_fingerprint())
        history.append({"role": "user", "content": f"вопрос {index}"})
        history.append({"role": "assistant", "content": f"ответ {index}"})

    assert len(fingerprints) == 1


def test_user_message_goes_last_in_the_volatile_layer():
    layers = agent.build_layers(
        user_message="мне тревожно",
        rag_fragments=["Урок про тревогу"],
        last_bot_reply="прошлая реплика",
    )
    content = layers.volatile[-1].content

    assert content.rstrip().endswith("мне тревожно")
    assert "Урок про тревогу" in content


def test_rag_absence_is_stated_explicitly():
    content = agent.build_layers(user_message="привет").volatile[-1].content

    assert "Обучающих фрагментов по теме не найдено." in content


def test_daily_context_lands_in_volatile_layer_not_the_prefix():
    base = agent.build_layers(user_message="привет")
    withctx = agent.build_layers(
        user_message="привет",
        daily_context="Контекст дня: сегодня день диализа; утренние лекарства не отмечены.",
    )

    assert "сегодня день диализа" in withctx.volatile[-1].content
    assert "сегодня день диализа" not in base.volatile[-1].content
    # день меняется — префикс (system+profile+summary) обязан остаться прежним
    assert base.prefix_fingerprint() == withctx.prefix_fingerprint()
    # реплика пациента всё равно последняя
    assert withctx.volatile[-1].content.rstrip().endswith("привет")


# --------------------------------------------------------------------------- #
# Agent.run()
# --------------------------------------------------------------------------- #

class _StubClient:
    account_id = "A1-pro"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    async def structured(self, messages, system_prompt, schema, **kwargs):
        self.calls.append({"messages": messages, "system": system_prompt, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def call_with_functions(self, messages, system_prompt, **kwargs):
        # Инструменты всегда включены — модель просто решает их не звать.
        return FunctionCallResult(
            content="", function_call=None, functions_state_id=None, finish_reason="stop"
        )


@pytest.fixture()
def stub_client(monkeypatch):
    holder: dict = {}

    def _install(*outcomes):
        client = _StubClient(outcomes)
        holder["client"] = client

        async def fake_get_available(model_tier, *, allow_fallback=False, sticky_key=None):
            holder["sticky_key"] = sticky_key
            holder["tier"] = model_tier
            return client

        monkeypatch.setattr(agent.loop.pool, "get_available", fake_get_available)
        return client

    holder["install"] = _install
    return holder


@pytest.mark.asyncio
async def test_agent_run_makes_a_single_llm_call(stub_client):
    client = stub_client["install"](
        StructuredResult(
            parsed=AgentReply.model_validate(_reply_payload()),
            raw_text="{}",
            tokens_in=800,
            tokens_out=120,
            latency_ms=900,
        )
    )
    layers = agent.build_layers(user_message="мне тревожно")

    run = await agent.Agent().run(layers, patient_id=7, thread_key="p7-default")

    assert run.ok
    assert run.llm_calls == 1
    assert run.repair_attempts == 0
    assert run.reply.intent == "emotional_support"
    assert run.tokens_in == 800
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_agent_run_uses_thread_key_for_sticky_and_fingerprint_for_cache(stub_client):
    client = stub_client["install"](
        StructuredResult(parsed=AgentReply.model_validate(_reply_payload()), raw_text="{}")
    )
    layers = agent.build_layers(user_message="мне тревожно")

    run = await agent.Agent().run(layers, patient_id=7, thread_key="p7-default")

    assert stub_client["sticky_key"] == "p7-default"
    assert client.calls[0]["session_id"] == f"p7-default-{run.prefix_fp}"
    assert client.calls[0]["step"] == "agent"


@pytest.mark.asyncio
async def test_agent_run_retries_once_then_reports_failure(stub_client):
    stub_client["install"](
        LLMResponseError("schema validation failed twice"),
        LLMResponseError("schema validation failed twice"),
    )
    layers = agent.build_layers(user_message="мне тревожно")

    run = await agent.Agent().run(layers, patient_id=7, thread_key="p7-default")

    assert run.ok is False
    assert run.reply is None
    assert run.attempts == 2
    assert "schema validation failed" in run.error


@pytest.mark.asyncio
async def test_agent_run_recovers_on_second_attempt(stub_client):
    stub_client["install"](
        LLMResponseError("schema validation failed twice"),
        StructuredResult(parsed=AgentReply.model_validate(_reply_payload()), raw_text="{}"),
    )
    layers = agent.build_layers(user_message="мне тревожно")

    run = await agent.Agent().run(layers, patient_id=7, thread_key="p7-default")

    assert run.ok
    assert run.attempts == 2


# --------------------------------------------------------------------------- #
# Маршрутизация в агента
# --------------------------------------------------------------------------- #

def _context(request_type: RequestType) -> PipelineContext:
    context = PipelineContext(
        request=LLMRequest(patient_id=1, user_input="текст", thread_id="default")
    )
    context.classification = RouterResult(
        request_type=request_type,
        model_tier=ModelTier.PRO,
        domain_hint=None,
        priority=2,
    )
    return context


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("emotional_support", ["emotional_support"]),
        ("education", ["education"]),
        ("smalltalk", []),
        ("safety", ["safety"]),
        ("что-то новое", []),
    ],
)
def test_intent_maps_to_legacy_agent_names(intent, expected):
    assert supervisor_stage._agent_intent_to_agents(intent) == expected


@pytest.mark.asyncio
async def test_agent_failure_does_not_fall_back_to_legacy_branch(monkeypatch, stub_client):
    """Живым прогоном (фаза 1, LLM_test/reports/2026.08.24_21.59.md, ходы
    1/6/7) откат на старую ветку при сбое карточки маскировал сбой статистикой
    intake→delegation→expert и утраивал латентность хода. Ветка не откатывается
    на неё — отдаёт пациенту технический ответ сама."""
    stub_client["install"](
        LLMResponseError("schema validation failed twice"),
        LLMResponseError("schema validation failed twice"),
    )

    context = await supervisor_stage.SupervisorStage().process(_context(RequestType.EMOTIONAL))

    assert context.diagnostics["supervisor"]["branch"] == "single_agent"
    assert context.diagnostics["supervisor"]["graph_path"] == ["agent"]
    assert context.diagnostics["supervisor"]["error"] is not None
    assert context.response_draft == supervisor_stage._AGENT_ERROR_REPLY
    assert "single_agent_fallback" not in context.diagnostics


# --------------------------------------------------------------------------- #
# Судья
# --------------------------------------------------------------------------- #

def test_judge_schema_is_flat_and_required():
    schema = structured.json_schema_for(JudgeVerdict)

    structured.assert_required_present(schema)
    assert "$ref" not in json.dumps(schema, ensure_ascii=False)


def test_judge_total_sums_four_scales():
    verdict = JudgeVerdict.model_validate(
        {
            "relevance": 5,
            "safety": 4,
            "tone": 3,
            "actionability": 2,
            "violations": [],
            "comment": "ок",
        }
    )

    assert verdict.total == 14


def test_system_prompt_lists_the_exact_json_keys():
    """Без явного перечисления GigaChat придумывает свои имена полей."""
    from app.llm.agent.prompts import AGENT_SYSTEM_PROMPT
    from app.llm.agent.schemas import AGENT_REPLY_KEYS

    assert AGENT_REPLY_KEYS in AGENT_SYSTEM_PROMPT
    for key in structured.json_schema_for(AgentReply)["properties"]:
        assert key in AGENT_SYSTEM_PROMPT


def test_judge_scores_are_integers_not_strings():
    props = structured.json_schema_for(JudgeVerdict)["properties"]

    for scale in ("relevance", "safety", "tone", "actionability"):
        assert props[scale]["type"] == "integer"
        assert props[scale]["minimum"] == 1
        assert props[scale]["maximum"] == 5


# --------------------------------------------------------------------------- #
# Библиотека техник
# --------------------------------------------------------------------------- #

def test_technique_block_offers_candidates_for_anxiety():
    block = agent.techniques.build_technique_block(user_message="мне очень тревожно и страшно")

    assert block
    assert "technique_id" in block
    assert "[p" in block


def test_technique_block_is_empty_for_neutral_message():
    assert agent.techniques.build_technique_block(user_message="спасибо, всё понятно") == ""


def test_active_interactive_technique_injects_the_current_step():
    from app.llm.technique_library import get_techniques, infer_arousal, infer_emotions

    cards = [
        c
        for c in get_techniques(infer_emotions("мне тревожно"), infer_arousal("мне тревожно"))
        if c.interactive and c.steps
    ]
    if not cards:
        pytest.skip("в библиотеке нет интерактивных техник для тревоги")
    card = cards[0]

    block = agent.techniques.build_technique_block(
        user_message="ладно, попробовал",
        state=agent.TechniqueState(current_id=card.id, step_index=1),
    )

    assert f"АКТИВНАЯ ТЕХНИКА [{card.id}]" in block
    assert card.steps[1] in block
    assert "Не предлагай другую технику" in block


def test_finished_technique_asks_about_the_effect():
    from app.llm.technique_library import get_techniques, infer_arousal, infer_emotions

    cards = [
        c
        for c in get_techniques(infer_emotions("мне тревожно"), infer_arousal("мне тревожно"))
        if c.interactive and c.steps
    ]
    if not cards:
        pytest.skip("в библиотеке нет интерактивных техник для тревоги")
    card = cards[0]

    block = agent.techniques.build_technique_block(
        user_message="сделал",
        state=agent.TechniqueState(current_id=card.id, step_index=len(card.steps)),
    )

    assert "ПРОЙДЕНА ЦЕЛИКОМ" in block
    assert "Новую технику сейчас не предлагай" in block


def test_advance_ignores_absent_technique():
    state = agent.TechniqueState(current_id="p02", step_index=2, turns=3, recent_ids=["p02"])

    for value in ("нет", "", "  ", None):
        assert agent.advance_technique(state, value) is state


def test_advance_ignores_unknown_id():
    state = agent.TechniqueState()

    assert agent.advance_technique(state, "p999") is state


def test_advance_starts_and_progresses_interactive_technique():
    from app.llm.technique_library import TECHNIQUE_LIBRARY

    card = next((c for c in TECHNIQUE_LIBRARY if c.interactive and len(c.steps) >= 2), None)
    if card is None:
        pytest.skip("в библиотеке нет интерактивных техник")

    first = agent.advance_technique(agent.TechniqueState(), card.id)
    assert first.current_id == card.id
    assert first.step_index == 1
    assert first.turns == 1
    assert first.recent_ids == [card.id]

    second = agent.advance_technique(first, card.id)
    assert second.step_index == 2
    assert second.turns == 2
    assert second.recent_ids == [card.id]


def test_advance_caps_step_index_at_the_last_step():
    from app.llm.technique_library import TECHNIQUE_LIBRARY

    card = next((c for c in TECHNIQUE_LIBRARY if c.interactive and c.steps), None)
    if card is None:
        pytest.skip("в библиотеке нет интерактивных техник")

    state = agent.TechniqueState(current_id=card.id, step_index=len(card.steps), recent_ids=[card.id])

    assert agent.advance_technique(state, card.id).step_index == len(card.steps)


def test_switching_technique_resets_progress():
    from app.llm.technique_library import TECHNIQUE_LIBRARY

    if len(TECHNIQUE_LIBRARY) < 2:
        pytest.skip("нужно минимум две техники")
    first, second = TECHNIQUE_LIBRARY[0], TECHNIQUE_LIBRARY[1]

    state = agent.TechniqueState(current_id=first.id, step_index=2, turns=3, recent_ids=[first.id])
    switched = agent.advance_technique(state, second.id)

    assert switched.current_id == second.id
    assert switched.turns == 1
    assert switched.recent_ids == [first.id, second.id]


def test_technique_id_is_part_of_the_schema_and_prompt():
    from app.llm.agent.prompts import AGENT_SYSTEM_PROMPT

    schema = structured.json_schema_for(AgentReply)
    assert "technique_id" in schema["properties"]
    assert "technique_id" in AGENT_SYSTEM_PROMPT
    assert "Одна техника за ход" in AGENT_SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# Второй эшелон: вердикт агента как сеть под ложноотрицательные L0
# --------------------------------------------------------------------------- #

from app.llm import safety_responses  # noqa: E402
from app.llm.pipeline.stages.supervisor import _apply_agent_safety_net  # noqa: E402


class _L0(dict):
    """Мини-заглушка решения L0: важен только safety_level."""

    def __init__(self, level: str):
        super().__init__()
        self.safety_level = level


def _ctx_with_l0(level: str | None) -> PipelineContext:
    context = PipelineContext(request=LLMRequest(patient_id=1, user_input="текст"))
    context.l0 = _L0(level) if level else None
    return context


def _card(**overrides) -> AgentReply:
    return AgentReply.model_validate(_reply_payload(**overrides))


def test_agent_urgent_overrides_the_reply():
    """Текст уже сгенерирован — выбрасываем его и подставляем протокол."""
    card = _card(
        safety_level="urgent",
        safety_kind="psychological",
        reply="давай подышим вместе",
    )

    result = _apply_agent_safety_net(_ctx_with_l0("none"), card)

    assert result["reply_overridden"] is True
    assert result["reply"] == safety_responses.CRISIS_RESPONSE
    assert "давай подышим" not in result["reply"]


def test_medical_urgent_gets_the_ambulance_text_not_the_hotline():
    """Телефон доверия при передозировке — вредный совет."""
    card = _card(**{"safety_level": "urgent", "safety_kind": "medical"})

    result = _apply_agent_safety_net(_ctx_with_l0("none"), card)

    assert result["reply"] == safety_responses.MEDICAL_URGENT_RESPONSE
    assert "103" in result["reply"]
    assert "8-800-2000-122" not in result["reply"]


def test_l0_miss_is_recorded_when_agent_sees_more():
    """Ход, где L0 промолчал, а агент увидел риск, — это пропуск L0."""
    result = _apply_agent_safety_net(_ctx_with_l0("none"), _card(safety_level="concern"))

    assert result["missed_by_l0"] is True
    assert result["reply_overridden"] is False
    assert result["l0_level"] == "none"
    assert result["agent_level"] == "concern"


def test_no_miss_when_l0_already_saw_it():
    result = _apply_agent_safety_net(_ctx_with_l0("concern"), _card(safety_level="concern"))

    assert result["missed_by_l0"] is False


def test_agent_quieter_than_l0_is_not_a_miss():
    """L0 поднял тревогу, агент нет — это не пропуск L0, а его перестраховка."""
    result = _apply_agent_safety_net(_ctx_with_l0("concern"), _card(safety_level="none"))

    assert result["missed_by_l0"] is False
    assert result["reply_overridden"] is False


def test_ordinary_turn_passes_the_reply_through():
    card = _card()

    result = _apply_agent_safety_net(_ctx_with_l0(None), card)

    assert result["reply"] == card.reply.strip()
    assert result["reply_overridden"] is False
    assert result["missed_by_l0"] is False


def test_safety_kind_offers_the_right_values():
    props = structured.json_schema_for(AgentReply)["properties"]

    assert props["safety_kind"]["enum"] == ["psychological", "medical", "none"]
