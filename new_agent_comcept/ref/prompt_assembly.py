"""
Сборка промпта под префиксное кэширование GigaChat.

ГЛАВНАЯ ИДЕЯ
------------
Кэш GigaChat — префиксный. Сервер переиспользует посчитанный контекст, если
запрос приходит с тем же X-Session-ID и НАЧАЛО messages байт-в-байт совпадает
с предыдущим. Первое же расхождение обнуляет кэш на весь хвост.

Отсюда единственное архитектурное правило, из которого следует всё остальное:

    messages собираются строго по убыванию стабильности,
    и ничто выше волатильного слоя не меняется в течение сессии.

Слои:

    [0] SYSTEM      — константа релиза. Меняется только при деплое.
    [1] PROFILE     — паспорт пациента. Меняется раз в сутки/на событие.
    [2] SUMMARY     — свёрнутая история. Меняется раз в N ходов.
    [3] WINDOW      — последние ходы дословно. Растёт в конце.
    [4] VOLATILE    — RAG-выдача, инструкция шага, текущая реплика.

Слой 4 всегда последний. Слой 3 только дописывается в конец. Слои 0-2
пересобираются редко и полностью — при пересборке кэш обнуляется осознанно,
а не случайно.

ЧАСТЫЕ ОШИБКИ, КОТОРЫЕ УБИВАЮТ КЭШ (и деньги)
---------------------------------------------
  * timestamp / «сегодня 14:32» в system-промпте;
  * json.dumps(dict) без sort_keys — порядок ключей плавает;
  * RAG-контекст, вклеенный в system;
  * uuid запроса внутри текста промпта;
  * разный system-промпт на каждый шаг мультиагентной цепочки при общем
    session_id: каждый шаг сбрасывает кэш следующему.

ДИАГНОСТИКА
-----------
Если usage.precached_prompt_tokens ≈ 0 на втором и последующих ходах —
кэш не работает. Ищите нестабильный байт в префиксе.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

Role = Literal["system", "user", "assistant", "function"]


def canonical_json(obj: Any) -> str:
    """Детерминированная сериализация. Без неё префикс «дышит»."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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

    system: str                                   # [0]
    profile: str = ""                             # [1]
    summary: str = ""                             # [2]
    window: list[Turn] = field(default_factory=list)   # [3]
    volatile: list[Turn] = field(default_factory=list) # [4]

    def prefix_fingerprint(self) -> str:
        """
        Отпечаток стабильной части. Логируйте его вместе с usage:
        если отпечаток изменился, а вы этого не планировали — вот и утечка.
        """
        h = hashlib.sha256()
        for part in (self.system, self.profile, self.summary):
            h.update(part.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()[:16]

    def build(self) -> list[dict[str, Any]]:
        """
        GigaChat принимает ровно один system-message и только первым.
        Поэтому profile и summary идут не системными, а «предысторией»:
        user-реплика с данными + короткое подтверждение ассистента.
        Такая пара стабильна и отлично ложится в префикс.
        """
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system}]

        stable_blocks: list[str] = []
        if self.profile:
            stable_blocks.append(f"<профиль_пациента>\n{self.profile}\n</профиль_пациента>")
        if self.summary:
            stable_blocks.append(f"<итог_предыдущих_бесед>\n{self.summary}\n</итог_предыдущих_бесед>")

        if stable_blocks:
            messages.append({"role": "user", "content": "\n\n".join(stable_blocks)})
            messages.append({"role": "assistant", "content": "Принято. Учитываю эти данные."})

        messages.extend(t.to_message() for t in self.window)
        messages.extend(t.to_message() for t in self.volatile)
        return messages


# --------------------------------------------------------------------------- #
# Session ID
# --------------------------------------------------------------------------- #

def session_key(patient_id: int, thread_id: str, prefix_fingerprint: str) -> str:
    """
    Ключ кэша.

    Отпечаток входит в ключ намеренно: если стабильная часть изменилась
    (новый релиз системного промпта, обновился профиль), старый кэш всё равно
    бесполезен. Новый ключ = чистый старт вместо частичных совпадений и
    непредсказуемого биллинга.
    """
    return f"p{patient_id}-{thread_id}-{prefix_fingerprint}"


# --------------------------------------------------------------------------- #
# Окно диалога
# --------------------------------------------------------------------------- #

def trim_window(
    window: Iterable[Turn],
    *,
    max_turns: int = 12,
    max_chars: int = 6000,
) -> tuple[list[Turn], list[Turn]]:
    """
    Разделить окно на «оставить» и «вытеснить в summary».

    Обрезаем ТОЛЬКО с головы и ТОЛЬКО парами (user+assistant): обрыв на
    середине пары ломает логику диалога, а не только кэш.

    Возвращает (kept, evicted). Evicted идёт в сумматор эпизодической памяти.
    """
    turns = list(window)
    if len(turns) <= max_turns and sum(len(t.content) for t in turns) <= max_chars:
        return turns, []

    kept = turns[-max_turns:]
    # выравниваем: окно должно начинаться с реплики пользователя
    while kept and kept[0].role != "user":
        kept.pop(0)
    while sum(len(t.content) for t in kept) > max_chars and len(kept) > 2:
        kept.pop(0)
        while kept and kept[0].role != "user":
            kept.pop(0)

    evicted = turns[: len(turns) - len(kept)]
    return kept, evicted


def approx_tokens(text: str) -> int:
    """
    Грубая оценка: ~3.5 символа на токен для русского.
    Для биллинга не годится — используйте GigaChatClient.count_tokens().
    Годится для быстрых проверок бюджета в рантайме.
    """
    return max(1, round(len(text) / 3.5))
