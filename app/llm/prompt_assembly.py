"""
Сборка промпта по слоям под префиксное кэширование GigaChat.

ГЛАВНАЯ ИДЕЯ
------------
Кэш GigaChat — префиксный. Сервер переиспользует посчитанный контекст, если
запрос приходит с тем же ``X-Session-ID`` и НАЧАЛО ``messages`` байт-в-байт
совпадает с предыдущим. Первое же расхождение обнуляет кэш на весь хвост.

    messages собираются строго по убыванию стабильности,
    и ничто выше волатильного слоя не меняется в течение сессии.

    [0] SYSTEM   — константа релиза. Меняется только при деплое.
    [1] PROFILE  — паспорт пациента. Меняется раз в сутки / на событие.
    [2] SUMMARY  — свёрнутая история. Меняется раз в N ходов.
    [3] WINDOW   — последние ходы дословно. Растёт в КОНЦЕ.
    [4] VOLATILE — RAG-выдача, инструкция шага, текущая реплика, repair-инструкция.

Слой 4 всегда последний, слой 3 только дописывается в конец. Слои 0-2
пересобираются редко и целиком — при пересборке кэш обнуляется осознанно
(меняется ``prefix_fingerprint()``, а значит и ключ сессии).

ОТКЛЮЧАЕМОСТЬ
-------------
Модуль — новая ветка рядом со старой. Включается переменной окружения
``LLM_PROMPT_LAYERS=1``; при выключенном флаге вызывающий код собирает
``messages`` как раньше (см. ``policy._call_structured_llm``).

Референс: ``new_agent_comcept/ref/prompt_assembly.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

Role = Literal["system", "user", "assistant", "function"]

ENV_FLAG = "LLM_PROMPT_LAYERS"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Подтверждение ассистента после стабильного блока. Константа: любая
# вариативность здесь ломает префикс.
STABLE_ACK = "Принято. Учитываю эти данные."

DEFAULT_WINDOW_TURNS = 12
DEFAULT_WINDOW_CHARS = 6000


def layers_enabled() -> bool:
    """Включена ли послойная сборка промпта (флаг окружения)."""
    return str(os.getenv(ENV_FLAG, "")).strip().lower() in _TRUTHY


# --------------------------------------------------------------------------- #
# Детерминированная сериализация
# --------------------------------------------------------------------------- #

def canonical_json(obj: Any) -> str:
    """Детерминированная сериализация. Без неё префикс «дышит»."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_DECIMAL_RE = re.compile(r"(?<![\d,.])(\d+)[.,](\d+)(?![\d,.])")


def stable_number(value: float | int | str) -> str:
    """Каноническое представление числа: точка-разделитель, без хвостовых нулей.

    ``36.60``, ``36,6`` и ``36.6`` — три разных набора байт для одного значения.
    Для префикса это три разных промпта.
    """
    text = str(value).strip().replace(",", ".")
    if "." not in text:
        return text
    integer, _, fraction = text.partition(".")
    fraction = fraction.rstrip("0")
    if not fraction:
        return integer or "0"
    return f"{integer or '0'}.{fraction}"


def canonical_line(text: str) -> str:
    """Схлопывает пробелы и нормализует десятичные числа в строке."""
    compact = " ".join(str(text or "").split())
    return _DECIMAL_RE.sub(lambda m: stable_number(f"{m.group(1)}.{m.group(2)}"), compact)


# --------------------------------------------------------------------------- #
# Аудит стабильных слоёв
# --------------------------------------------------------------------------- #

_UNSTABLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("uuid", re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    ("time_of_day", re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b")),
    ("iso_datetime", re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")),
    ("epoch_or_ms", re.compile(r"\b1[0-9]{9,12}\b")),
    ("float_tail", re.compile(r"\d+\.\d*0(?!\d)")),
)


def find_unstable_fragments(text: str) -> list[tuple[str, str]]:
    """Ищет в тексте то, что убивает префиксный кэш.

    Возвращает список ``(тип, найденный фрагмент)``. Используется в тестах как
    страж стабильных слоёв: в слоях 0-2 результат обязан быть пустым.
    """
    found: list[tuple[str, str]] = []
    for name, pattern in _UNSTABLE_PATTERNS:
        for match in pattern.finditer(str(text or "")):
            found.append((name, match.group(0)))
    return found


# --------------------------------------------------------------------------- #
# Слои
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class Turn:
    role: Role
    content: str
    functions_state_id: str | None = None
    function_call: dict[str, Any] | None = None

    def to_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.role == "assistant":
            if self.functions_state_id:
                msg["functions_state_id"] = self.functions_state_id
            if self.function_call:
                msg["function_call"] = self.function_call
        return msg


@dataclass(slots=True)
class PromptLayers:
    """Слои промпта, каждый со своим сроком жизни."""

    system: str                                          # [0]
    profile: str = ""                                    # [1]
    summary: str = ""                                    # [2]
    window: list[Turn] = field(default_factory=list)     # [3]
    volatile: list[Turn] = field(default_factory=list)   # [4]

    def prefix_fingerprint(self) -> str:
        """Отпечаток стабильной части (слои 0-2).

        Логируется вместе с usage: если отпечаток изменился, а этого не
        планировали — вот и утечка нестабильного байта в префикс.
        """
        h = hashlib.sha256()
        for part in (self.system, self.profile, self.summary):
            h.update(part.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()[:16]

    def stable_blocks(self) -> list[str]:
        blocks: list[str] = []
        if self.profile:
            blocks.append(f"<профиль_пациента>\n{self.profile}\n</профиль_пациента>")
        if self.summary:
            blocks.append(f"<итог_предыдущих_бесед>\n{self.summary}\n</итог_предыдущих_бесед>")
        return blocks

    def build(self) -> list[dict[str, Any]]:
        """Полный список messages, включая system первым сообщением.

        GigaChat принимает ровно один system-message и только первым (иначе 422).
        Поэтому профиль и свёртка идут не системными, а «предысторией»:
        user-реплика с данными + короткое подтверждение ассистента.
        """
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system}]
        blocks = self.stable_blocks()
        if blocks:
            messages.append({"role": "user", "content": "\n\n".join(blocks)})
            messages.append({"role": "assistant", "content": STABLE_ACK})
        messages.extend(t.to_message() for t in self.window)
        messages.extend(t.to_message() for t in self.volatile)
        return messages

    def tail_messages(self) -> list[dict[str, Any]]:
        """Всё после system — то, что ``GigaChatClient.call()`` принимает как messages."""
        return self.build()[1:]


# --------------------------------------------------------------------------- #
# Session ID
# --------------------------------------------------------------------------- #

def with_fingerprint(thread_key: str, prefix_fingerprint: str) -> str:
    """Ключ кэша: готовый ключ треда (``p{id}-{thread}``, см. ``pool.session_key``)
    плюс отпечаток стабильной части промпта.

    Отдельно от ключа треда, а не единой функцией с патентом/тредом на входе:
    sticky-роутинг аккаунта (``pool.get_available(sticky_key=...)``) должен
    видеть один и тот же ключ для всего треда, а кэш-ключ — свой на каждый
    узел/агента с его системным промптом. Разные узлы графа имеют разные
    системные промпты, значит и разные отпечатки — каждый узел получает свою
    кэш-дорожку внутри одного треда, но остаётся на одном аккаунте.

    Отпечаток входит в ключ намеренно: если стабильная часть изменилась
    (новый релиз системного промпта, обновился профиль), старый кэш всё равно
    бесполезен. Новый ключ = чистый старт вместо частичных совпадений и
    непредсказуемого биллинга.
    """
    key = str(thread_key or "").strip()
    if not key:
        return ""
    if not prefix_fingerprint:
        return key
    return f"{key}-{prefix_fingerprint}"


# --------------------------------------------------------------------------- #
# Окно диалога
# --------------------------------------------------------------------------- #

def trim_window(
    window: Iterable[Turn],
    *,
    max_turns: int = DEFAULT_WINDOW_TURNS,
    max_chars: int = DEFAULT_WINDOW_CHARS,
) -> tuple[list[Turn], list[Turn]]:
    """Разделить окно на «оставить» и «вытеснить в свёртку».

    Обрезаем ТОЛЬКО с головы и ТОЛЬКО парами (user+assistant): обрыв на
    середине пары ломает логику диалога, а не только кэш.
    """
    turns = list(window)
    if len(turns) <= max_turns and sum(len(t.content) for t in turns) <= max_chars:
        return turns, []

    kept = turns[-max_turns:]
    while kept and kept[0].role != "user":
        kept.pop(0)
    while sum(len(t.content) for t in kept) > max_chars and len(kept) > 2:
        kept.pop(0)
        while kept and kept[0].role != "user":
            kept.pop(0)

    evicted = turns[: len(turns) - len(kept)]
    return kept, evicted


def approx_tokens(text: str) -> int:
    """Грубая оценка: ~3.5 символа на токен для русского. Не для биллинга."""
    return max(1, round(len(text) / 3.5))


def window_from_history(
    history: Iterable[dict[str, Any]] | None,
    *,
    max_turns: int = DEFAULT_WINDOW_TURNS,
    max_chars: int = DEFAULT_WINDOW_CHARS,
    exclude_last_user_message: str | None = None,
) -> list[Turn]:
    """Строит слой [3] из истории чата (``context['chat_history']``).

    История приходит в хронологическом порядке. Текущая реплика пользователя
    в окно не попадает — она живёт в волатильном слое; если вызывающий код
    уже успел записать её в историю, передайте её в
    ``exclude_last_user_message``.
    """
    turns: list[Turn] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        turns.append(Turn(role=role, content=content))  # type: ignore[arg-type]

    current = str(exclude_last_user_message or "").strip()
    if current and turns and turns[-1].role == "user" and turns[-1].content == current:
        turns.pop()

    kept, _ = trim_window(turns, max_turns=max_turns, max_chars=max_chars)
    return kept


# --------------------------------------------------------------------------- #
# Слой [1]: профиль пациента
# --------------------------------------------------------------------------- #

# Порядок фиксирован: перестановка секций меняет байты префикса.
# Осознанно НЕ входят в профиль:
#   rag_context / rag_views / rag_grounding_items — меняются каждый ход → слой [4];
#   chat_history                                  — слой [3];
#   active_practices                              — всегда пусто (заглушка в context_builder).
PROFILE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("patient_summary", "Краткая сводка за последние дни"),
    ("stable_facts", "Устойчивые факты о пациенте"),
    ("recent_vitals", "Витальные показатели"),
    ("medication_adherence", "Приём лекарств"),
    ("sleep_summary", "Сон"),
    ("last_scale_scores", "Шкалы"),
    ("recent_weight", "Вес"),
    ("recent_water", "Потребление воды"),
    ("routine_summary", "Рутина"),
    ("practices_summary", "Практики"),
)

_LIST_SECTIONS = frozenset({"patient_summary", "stable_facts"})


def build_profile_layer(context: dict[str, Any] | None) -> str:
    """Стабильное представление данных пациента (слой [1]).

    Аналог ``context_builder.format_context_for_llm()``, но:
      * без RAG-секции — она волатильна и обнуляет весь хвост;
      * с фиксированным порядком секций;
      * с канонизацией чисел и пробелов.
    """
    if not context:
        return ""

    lines: list[str] = []
    for key, label in PROFILE_SECTIONS:
        values = context.get(key) or []
        if not isinstance(values, (list, tuple)):
            values = [values]
        rendered = [canonical_line(str(v)) for v in values if str(v).strip()]
        if not rendered:
            continue
        if key in _LIST_SECTIONS:
            lines.append(f"{label}:")
            lines.extend(f"  - {item}" for item in rendered)
        else:
            lines.append(f"{label}: {', '.join(rendered)}")

    if not lines:
        return ""
    return "Данные пациента:\n" + "\n".join(lines)


# --------------------------------------------------------------------------- #
# Слой [2]: свёртка
# --------------------------------------------------------------------------- #

def build_summary_layer(*, anchor_goal: str | None = None, digest: str | None = None) -> str:
    """Стабильное представление свёрнутой истории (слой [2]).

    Сейчас сюда попадает только якорная цель сессии: она ставится один раз и
    больше не переписывается. Всё, что меняется каждый ход (план хода, статус
    ветки, накопленный intake-контекст, активная техника), живёт в слое [4] —
    иначе отпечаток менялся бы на каждом ходу и кэш не набирался бы никогда.

    ``digest`` — свёртка вытесненных из окна ходов, читается из
    ``llm.chat_summaries`` фоновой задачей ``app.llm.memory_store.maybe_compact``
    (шаг 5).
    """
    parts: list[str] = []
    anchor = canonical_line(str(anchor_goal or ""))
    if anchor and anchor.lower() != "не обозначена":
        parts.append(f"Якорная цель сессии: {anchor}")
    digest_text = str(digest or "").strip()
    if digest_text:
        parts.append(digest_text)
    return "\n".join(parts)
