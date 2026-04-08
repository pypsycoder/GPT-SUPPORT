"""Helpers for short-answer normalization and pending-question slot fill."""

from __future__ import annotations

import re
from typing import Any

from app.llm.supervisor.models import PendingQuestion

_YES_VALUES = {"да", "ага", "угу", "конечно", "скорее да", "пожалуй да"}
_NO_VALUES = {"нет", "неа", "не", "скорее нет", "пожалуй нет"}
_UNKNOWN_VALUES = {"не знаю", "не уверен", "не уверена", "затрудняюсь", "не помню", "не понял"}
_FUZZY_VALUES = {"иногда", "вроде", "кажется", "наверное", "примерно", "может быть", "как будто"}


# normalize_short_answer
def normalize_short_answer(text: str) -> dict[str, Any] | None:
    normalized = " ".join(str(text or "").lower().strip().split())
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


# try_parse_pending_answer
def try_parse_pending_answer(text: str, pending_question: PendingQuestion | None) -> dict[str, Any] | None:
    if pending_question is None:
        return None
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
