"""Тесты послойной сборки промпта (шаг 2: префиксное кэширование GigaChat)."""

from __future__ import annotations

import pytest

from app.llm import prompt_assembly as pa


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
