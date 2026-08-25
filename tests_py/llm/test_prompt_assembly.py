"""Тесты послойной сборки промпта (шаг 2: префиксное кэширование GigaChat)."""

from __future__ import annotations

import pytest

from app.llm import prompt_assembly as pa
from app.llm.langgraph_supervisor import policy
from app.llm.langgraph_supervisor.models import FirstModuleState
from app.llm.langgraph_supervisor.policy import build_prompt_layers
from app.llm.supervisor.models import CurrentState


SYSTEM = "Ты эксперт эмоциональной поддержки. Формат ответа: карточка."
PROFILE = "Данные пациента:\nСон: среднее 6.4ч, тренд стабильно"
SUMMARY = "Якорная цель сессии: страх перед фистулой"


def _layers(window_turns: int, *, volatile: str = "текущая реплика") -> pa.PromptLayers:
    window: list[pa.Turn] = []
    for index in range(window_turns):
        window.append(pa.Turn(role="user", content=f"реплика пациента {index}"))
        window.append(pa.Turn(role="assistant", content=f"ответ бота {index}"))
    return pa.PromptLayers(
        system=SYSTEM,
        profile=PROFILE,
        summary=SUMMARY,
        window=window,
        volatile=[pa.Turn(role="user", content=volatile)],
    )


# --------------------------------------------------------------------------- #
# Главный инвариант шага 2
# --------------------------------------------------------------------------- #

def test_growing_window_does_not_change_prefix_fingerprint():
    """Рост окна диалога не должен менять отпечаток стабильной части."""
    baseline = _layers(0).prefix_fingerprint()

    for turns in range(1, 12):
        assert _layers(turns).prefix_fingerprint() == baseline


def test_changing_volatile_layer_does_not_change_prefix_fingerprint():
    first = _layers(3, volatile="RAG-фрагмент А + реплика")
    second = _layers(3, volatile="совсем другой RAG-фрагмент + другая реплика")

    assert first.prefix_fingerprint() == second.prefix_fingerprint()


def test_growing_window_only_appends_to_the_tail():
    """Слой [3] дописывается в конец: общий префикс сообщений не сдвигается."""
    short = _layers(2).build()
    long = _layers(5).build()

    assert long[: len(short) - 1] == short[:-1]  # без волатильного хвоста


def test_changing_stable_layer_changes_prefix_fingerprint():
    baseline = _layers(2)
    changed = pa.PromptLayers(
        system=SYSTEM,
        profile=PROFILE + "\nВес: 71 кг",
        summary=SUMMARY,
        window=list(baseline.window),
        volatile=list(baseline.volatile),
    )

    assert changed.prefix_fingerprint() != baseline.prefix_fingerprint()


# --------------------------------------------------------------------------- #
# Ограничения GigaChat на system
# --------------------------------------------------------------------------- #

def test_exactly_one_system_message_and_it_is_first():
    messages = _layers(4).build()

    assert messages[0]["role"] == "system"
    assert sum(1 for m in messages if m["role"] == "system") == 1


def test_profile_and_summary_go_as_user_assistant_pair_after_system():
    messages = _layers(0).build()

    assert messages[1]["role"] == "user"
    assert "<профиль_пациента>" in messages[1]["content"]
    assert "<итог_предыдущих_бесед>" in messages[1]["content"]
    assert messages[2] == {"role": "assistant", "content": pa.STABLE_ACK}


def test_empty_stable_layers_produce_no_pseudo_dialog():
    messages = pa.PromptLayers(
        system=SYSTEM,
        volatile=[pa.Turn(role="user", content="привет")],
    ).build()

    assert messages == [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "привет"},
    ]


def test_tail_messages_drops_system():
    layers = _layers(2)

    assert layers.tail_messages() == layers.build()[1:]


def test_volatile_layer_is_always_last():
    messages = _layers(3, volatile="реплика хода").build()

    assert messages[-1] == {"role": "user", "content": "реплика хода"}


# --------------------------------------------------------------------------- #
# Канонизация
# --------------------------------------------------------------------------- #

def test_canonical_json_is_key_order_independent():
    assert pa.canonical_json({"b": 1, "a": 2}) == pa.canonical_json({"a": 2, "b": 1})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("36.60", "36.6"), ("36,6", "36.6"), ("70.0", "70"), ("6", "6"), ("0.50", "0.5")],
)
def test_stable_number(raw, expected):
    assert pa.stable_number(raw) == expected


def test_canonical_line_normalizes_numbers_and_whitespace():
    assert pa.canonical_line("Вес:  70.50   кг") == "Вес: 70.5 кг"


# --------------------------------------------------------------------------- #
# Слой [1]: профиль
# --------------------------------------------------------------------------- #

def _context() -> dict:
    return {
        "patient_summary": ["В последние дни сон ухудшился."],
        "recent_vitals": ["АД 150/90 (08.08)"],
        "sleep_summary": ["Сон: среднее 5.50ч, тренд снижается"],
        "recent_weight": ["Вес: 70.0 кг (08.08)"],
        "chat_history": [{"role": "user", "content": "привет"}],
        "rag_context": ["Урок «Калий». Релевантный фрагмент: ..."],
        "rag_grounding_items": [{"lesson_code": "01_potassium"}],
    }


def test_profile_layer_excludes_rag_and_history():
    profile = pa.build_profile_layer(_context())

    assert "Калий" not in profile
    assert "привет" not in profile
    assert "Сон: среднее 5.5ч" in profile
    assert "Вес: 70 кг" in profile


def test_profile_layer_is_deterministic_for_reordered_context():
    context = _context()
    reordered = dict(reversed(list(context.items())))

    assert pa.build_profile_layer(context) == pa.build_profile_layer(reordered)


def test_profile_layer_is_empty_without_data():
    assert pa.build_profile_layer({}) == ""
    assert pa.build_profile_layer(None) == ""


def test_stable_layers_contain_nothing_cache_hostile():
    """Страж: в слоях 0-2 не должно быть uuid, времени суток и хвостовых нулей."""
    layers = pa.PromptLayers(
        system=SYSTEM,
        profile=pa.build_profile_layer(_context()),
        summary=pa.build_summary_layer(anchor_goal="страх перед фистулой"),
    )

    for part in (layers.system, layers.profile, layers.summary):
        assert pa.find_unstable_fragments(part) == []


def test_find_unstable_fragments_detects_known_killers():
    kinds = {
        kind
        for kind, _ in pa.find_unstable_fragments(
            "Сегодня 14:32, запрос 123e4567-e89b-12d3-a456-426614174000, вес 70.0"
        )
    }

    assert {"uuid", "time_of_day", "float_tail"} <= kinds


# --------------------------------------------------------------------------- #
# Слой [2]: свёртка
# --------------------------------------------------------------------------- #

def test_summary_layer_skips_undefined_anchor():
    assert pa.build_summary_layer(anchor_goal="не обозначена") == ""
    assert pa.build_summary_layer(anchor_goal=None) == ""


def test_summary_layer_renders_anchor_goal():
    assert pa.build_summary_layer(anchor_goal="страх диализа") == "Якорная цель сессии: страх диализа"


# --------------------------------------------------------------------------- #
# Слой [3]: окно
# --------------------------------------------------------------------------- #

def test_window_from_history_keeps_order_and_roles():
    window = pa.window_from_history(
        [
            {"role": "user", "content": "первый вопрос"},
            {"role": "assistant", "content": "первый ответ"},
            {"role": "system", "content": "мусор"},
            {"role": "user", "content": ""},
        ]
    )

    assert [(t.role, t.content) for t in window] == [
        ("user", "первый вопрос"),
        ("assistant", "первый ответ"),
    ]


def test_window_from_history_drops_duplicate_of_current_message():
    window = pa.window_from_history(
        [
            {"role": "assistant", "content": "ответ бота"},
            {"role": "user", "content": "мне тревожно"},
        ],
        exclude_last_user_message="мне тревожно",
    )

    assert [t.content for t in window] == ["ответ бота"]


def test_trim_window_starts_from_user_turn():
    turns = [
        pa.Turn(role="user" if i % 2 == 0 else "assistant", content=f"реплика {i}")
        for i in range(20)
    ]

    kept, evicted = pa.trim_window(turns, max_turns=5)

    assert kept[0].role == "user"
    assert len(kept) + len(evicted) == len(turns)
    assert kept[-1] is turns[-1]


# --------------------------------------------------------------------------- #
# Ключ сессии
# --------------------------------------------------------------------------- #

def test_with_fingerprint_combines_thread_key_and_fingerprint():
    assert pa.with_fingerprint("p42-default", "abc123") == "p42-default-abc123"


def test_with_fingerprint_is_noop_without_fingerprint():
    assert pa.with_fingerprint("p42-default", "") == "p42-default"
    assert pa.with_fingerprint("", "abc123") == ""


# --------------------------------------------------------------------------- #
# Флаг окружения и интеграция с policy
# --------------------------------------------------------------------------- #

def test_layers_disabled_by_default(monkeypatch):
    monkeypatch.delenv(pa.ENV_FLAG, raising=False)
    assert pa.layers_enabled() is False

    monkeypatch.setenv(pa.ENV_FLAG, "1")
    assert pa.layers_enabled() is True

    monkeypatch.setenv(pa.ENV_FLAG, "off")
    assert pa.layers_enabled() is False


def _state(**kwargs) -> FirstModuleState:
    return FirstModuleState(
        user_message=kwargs.pop("user_message", "мне тревожно"),
        current_state=kwargs.pop("current_state", CurrentState()),
        message_type="full_message",
        model_tier="pro",
        **kwargs,
    )


def test_build_prompt_layers_puts_repair_instruction_into_volatile():
    state = _state(profile_block=PROFILE)
    state.current_state.anchor_goal = "страх диализа"

    clean = build_prompt_layers(state, system_prompt=SYSTEM, user_prompt="карточка")
    repaired = build_prompt_layers(
        state,
        system_prompt=SYSTEM,
        user_prompt="карточка",
        repair_instruction="\nИсправь предыдущую ошибку.",
    )

    # Repair-инструкция раньше дописывалась в system и обнуляла кэш на ретрае.
    assert repaired.system == clean.system
    assert repaired.prefix_fingerprint() == clean.prefix_fingerprint()
    assert "Исправь предыдущую ошибку." in repaired.volatile[-1].content


def test_build_prompt_layers_keeps_prefix_stable_as_history_grows():
    history: list[dict[str, str]] = []
    fingerprints = set()

    for index in range(5):
        state = _state(profile_block=PROFILE, history=list(history))
        state.current_state.anchor_goal = "страх диализа"
        layers = build_prompt_layers(state, system_prompt=SYSTEM, user_prompt=f"ход {index}")
        fingerprints.add(layers.prefix_fingerprint())
        history.append({"role": "user", "content": f"вопрос {index}"})
        history.append({"role": "assistant", "content": f"ответ {index}"})

    assert len(fingerprints) == 1


def test_build_prompt_layers_different_system_prompts_give_different_lanes():
    state = _state(profile_block=PROFILE)

    intake = build_prompt_layers(state, system_prompt="Ты intake-узел.", user_prompt="x")
    expert = build_prompt_layers(state, system_prompt="Ты эксперт.", user_prompt="x")

    assert intake.prefix_fingerprint() != expert.prefix_fingerprint()


@pytest.mark.parametrize(
    ("build_system", "build_repair"),
    [
        (policy.build_intake_system_prompt, policy._build_intake_retry_instruction),
        (policy.build_delegation_system_prompt, policy._build_delegation_retry_instruction),
        (policy.build_emotional_expert_system_prompt, policy._build_expert_retry_instruction),
        (policy.build_education_expert_system_prompt, policy._build_education_retry_instruction),
    ],
)
def test_legacy_system_prompt_is_byte_identical_after_split(build_system, build_repair):
    """Вынос repair-инструкции из системного промпта не меняет легаси-путь."""
    error = "missing required fields: Обоснование"

    assert build_system(error) == build_system() + build_repair(error)
    assert build_repair(None) == ""


class _FakeClient:
    account_id = "A1"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def call(self, messages, system_prompt, **kwargs):
        self.calls.append({"messages": messages, "system": system_prompt, **kwargs})
        return "Поддержка: ок", 10, 5, 7


@pytest.fixture()
def fake_client(monkeypatch):
    client = _FakeClient()

    async def fake_get_available(model_tier, *, allow_fallback=False, sticky_key=None):
        client.calls.append({"sticky_key": sticky_key})
        return client

    monkeypatch.setattr(policy.pool, "get_available", fake_get_available)
    return client


@pytest.mark.asyncio
async def test_call_structured_llm_legacy_path_unchanged(monkeypatch, fake_client):
    monkeypatch.delenv(pa.ENV_FLAG, raising=False)
    state = _state(profile_block=PROFILE, history=[{"role": "user", "content": "прошлый ход"}])
    state.session_id = "p7-default"

    await policy._call_structured_llm(
        system_prompt=SYSTEM,
        repair_instruction="\nИсправь ошибку.",
        user_prompt="карточка",
        model_tier="pro",
        strict_model_tier=False,
        temperature=0.2,
        session_id=state.session_id,
        state=state,
    )

    routing, call = fake_client.calls
    assert routing["sticky_key"] == "p7-default"
    assert call["system"] == SYSTEM + "\nИсправь ошибку."
    assert call["messages"] == [{"role": "user", "content": "карточка"}]
    assert call["session_id"] == "p7-default"
    assert call["prefix_fp"] is None
    assert state.prefix_fingerprints == []


@pytest.mark.asyncio
async def test_call_structured_llm_layered_path(monkeypatch, fake_client):
    monkeypatch.setenv(pa.ENV_FLAG, "1")
    state = _state(profile_block=PROFILE, history=[{"role": "user", "content": "прошлый ход"}])
    state.session_id = "p7-default"
    state.patient_id = 7

    await policy._call_structured_llm(
        system_prompt=SYSTEM,
        repair_instruction="\nИсправь ошибку.",
        user_prompt="карточка",
        model_tier="pro",
        strict_model_tier=False,
        temperature=0.2,
        session_id=state.session_id,
        state=state,
    )

    routing, call = fake_client.calls
    # Sticky-роутинг аккаунта остаётся на ключе треда без отпечатка.
    assert routing["sticky_key"] == "p7-default"
    assert call["system"] == SYSTEM
    assert call["patient_id"] == 7
    assert call["prefix_fp"] == state.prefix_fingerprints[0]
    assert call["session_id"] == f"p7-default-{call['prefix_fp']}"
    # Стабильная пара, окно, волатильная реплика с repair-инструкцией.
    assert call["messages"][0]["role"] == "user"
    assert "<профиль_пациента>" in call["messages"][0]["content"]
    assert call["messages"][1] == {"role": "assistant", "content": pa.STABLE_ACK}
    assert call["messages"][2] == {"role": "user", "content": "прошлый ход"}
    assert call["messages"][-1]["content"].endswith("Исправь ошибку.")
