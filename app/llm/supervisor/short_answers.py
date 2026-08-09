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


_EDUCATION_CLOSE_EXACT = frozenset({
    "нет", "неа", "не надо", "не хочу", "не интересно", "неинтересно",
    "хватит", "достаточно", "спасибо", "спс", "благодарю",
    "ладно", "ладно спасибо", "ок спасибо", "окей спасибо",
    "не нужно", "ненужно", "не надо спасибо",
    "пока", "всё", "все",
    "больше не надо", "больше не нужно",
    "не хочу знать", "не хочу больше",
})

_EDUCATION_NEUTRAL_ACK_EXACT = frozenset({
    "понятно", "ясно", "ок", "окей",
    "понял", "поняла",
    "понял спасибо", "поняла спасибо",
    "всё понятно", "все понятно",
    "всё ясно", "все ясно",
    "ясно спасибо", "понятно спасибо",
    "принял", "приняла",
    "усвоил", "усвоила",
})

_EDUCATION_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize_edu(text: str) -> str:
    """Normalize for education intent detection: lowercase + strip punctuation + collapse spaces."""
    lower = " ".join(str(text or "").lower().strip().split())
    return _EDUCATION_PUNCT_RE.sub("", lower).strip()


def is_education_close_intent(text: str) -> bool:
    """True если пользователь явно отказывается продолжать education-ветку."""
    normalized = _normalize_edu(text)
    if not normalized or len(normalized) > 50:
        return False
    return normalized in _EDUCATION_CLOSE_EXACT


_EDUCATION_CONFUSED_EXACT = frozenset({
    "не понял", "не поняла", "не понимаю", "не понятно", "непонятно",
    "объясни", "объясни проще", "объясни по-другому", "объясни иначе",
    "можешь проще", "можешь объяснить", "можешь пояснить",
    "поясни", "расскажи проще", "как это", "что это значит", "что значит",
    "не совсем понял", "не совсем поняла", "не очень понял", "не очень поняла",
    "что имеешь в виду", "что ты имеешь в виду",
    "сложно", "слишком сложно", "не очень понятно",
})

_EDUCATION_CONFUSED_PREFIXES = (
    "не понял",
    "не поняла",
    "не понимаю",
    "объясни",
    "поясни",
    "можешь объяснить",
    "можешь проще",
    "не совсем понял",
    "не совсем поняла",
)


def is_education_confused(text: str) -> bool:
    """True если пациент не понял объяснения и просит переформулировать."""
    normalized = _normalize_edu(text)
    if not normalized or len(normalized) > 80:
        return False
    if normalized in _EDUCATION_CONFUSED_EXACT:
        return True
    return any(normalized.startswith(p) for p in _EDUCATION_CONFUSED_PREFIXES)


def is_education_neutral_ack(text: str) -> bool:
    """True если пользователь нейтрально подтверждает что понял — без намерения продолжать.

    Используется только когда есть pending_question.reason == 'expert', т.е. бот предложил
    конкретный follow-up вопрос ("Хочешь узнать...?") и пациент ответил "понятно"/"ясно".
    """
    normalized = _normalize_edu(text)
    if not normalized or len(normalized) > 40:
        return False
    return normalized in _EDUCATION_NEUTRAL_ACK_EXACT


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
