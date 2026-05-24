"""Helpers for short-answer normalization and pending-question slot fill."""

from __future__ import annotations

import re
from typing import Any

from app.llm.supervisor.models import PendingQuestion

_YES_VALUES = {"да", "ага", "угу", "конечно", "скорее да", "пожалуй да"}
_NO_VALUES = {"нет", "неа", "не", "скорее нет", "пожалуй нет"}
_UNKNOWN_VALUES = {
    "не знаю",
    "не уверен",
    "не уверена",
    "затрудняюсь",
    "не помню",
    "не понял",
    "без понятия",
    "понятия не имею",
}
_FUZZY_VALUES = {"иногда", "вроде", "кажется", "наверное", "примерно", "может быть", "как будто"}
_UNKNOWN_PREFIXES = (
    "не знаю",
    "я не знаю",
    "сам не знаю",
    "не понимаю",
    "не могу объяснить",
    "не могу сказать",
    "не уверен",
    "не уверена",
    "затрудняюсь",
    "не понял",
    "без понятия",
    "понятия не имею",
)
_UNKNOWN_NON_SPECIFIC_TAIL_MARKERS = (
    "просто",
    "ничего не радует",
    "ничего не хочется",
    "все плохо",
    "как-то плохо",
    "грустно",
    "тяжело",
    "тревожно",
    "пусто",
)
_SPECIFIC_REASON_MARKERS = (
    "из-за",
    "из за",
    "потому что",
    "после",
    "перед",
    "когда",
    "на фоне",
    "ссор",
    "конфликт",
    "диализ",
    "операц",
    "болит",
    "давлен",
    "не сплю",
    "не спал",
    "завтрашн",
    "сегодня",
    "дома",
    "на работе",
    "в семье",
)


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").lower().strip().split())


def normalize_short_answer(text: str) -> dict[str, Any] | None:
    normalized = _normalize_text(text)
    if not normalized or len(normalized) > 40:
        return None
    if normalized in _UNKNOWN_VALUES:
        return {"kind": "unknown", "value": "unknown", "normalized": normalized}
    if normalized in _YES_VALUES:
        return {"kind": "yes_no", "value": True, "normalized": "yes"}
    if normalized in _NO_VALUES:
        return {"kind": "yes_no", "value": False, "normalized": "no"}
    if normalized in _FUZZY_VALUES:
        return {"kind": "fuzzy", "value": normalized, "normalized": normalized}
    if re.fullmatch(r"(10|[0-9])", normalized):
        return {"kind": "scale_0_10", "value": int(normalized), "normalized": normalized}
    return None


def is_unknown_reason_answer(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized or len(normalized) > 160:
        return False

    parsed = normalize_short_answer(normalized)
    if parsed is not None and parsed["kind"] == "unknown":
        return True

    prefix = next((item for item in _UNKNOWN_PREFIXES if normalized.startswith(item)), None)
    if not prefix:
        return False

    tail = normalized[len(prefix) :].strip(" .,!?:;-")
    if not tail:
        return True
    if any(marker in tail for marker in _SPECIFIC_REASON_MARKERS):
        return False
    if any(marker in tail for marker in _UNKNOWN_NON_SPECIFIC_TAIL_MARKERS):
        return True
    return False


def try_parse_pending_answer(text: str, pending_question: PendingQuestion | None) -> dict[str, Any] | None:
    if pending_question is None:
        return None
    raw_text = str(text or "").strip()
    if pending_question.expected_kind == "free_text":
        if not raw_text:
            return None
        return {
            "slot_name": pending_question.slot_name,
            "slot_value": raw_text,
            "answer_kind": "free_text",
            "normalized": raw_text,
        }

    parsed = normalize_short_answer(text)
    if parsed is None:
        return None

    compatible = {
        "yes_no": {"yes_no", "unknown"},
        "unknown": {"unknown"},
        "scale_0_10": {"scale_0_10", "unknown"},
        "fuzzy": {"fuzzy", "unknown"},
        "free_text": set(),
    }
    if parsed["kind"] not in compatible.get(pending_question.expected_kind, set()):
        return None

    return {
        "slot_name": pending_question.slot_name,
        "slot_value": parsed["value"],
        "answer_kind": parsed["kind"],
        "normalized": parsed["normalized"],
    }
