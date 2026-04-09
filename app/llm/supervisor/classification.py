"""Rule-based message classification for the stateful supervisor MVP."""

from __future__ import annotations

from typing import Any

from app.llm.supervisor.models import CurrentState
from app.llm.supervisor.short_answers import normalize_short_answer

_CORRECTION_MARKERS = (
    "точнее",
    "вернее",
    "исправлю",
    "я про",
    "не совсем",
    "не это",
)
_META_MESSAGES = {
    "спасибо",
    "ок",
    "окей",
    "понял",
    "поняла",
    "хорошо",
    "ладно",
    "ясно",
    "понятно",
    "угу",
    "ага",
    "да",
}
_INFORM_MARKERS = ("почему", "что это", "объясни", "объяснить", "нормально ли", "что со мной")
_PLAN_MARKERS = ("что делать", "как", "план", "следующий шаг", "с чего начать", "как быть")
_SUPPORT_MARKERS = ("плохо", "тяжело", "тревожно", "страшно", "поддерж", "помоги", "не справляюсь")
_HEALTH_MARKERS = (
    "диализ",
    "давление",
    "симптом",
    "боль",
    "таблет",
    "лекар",
    "фистул",
    "анализ",
    "почки",
)
_ROUTINE_MARKERS = ("режим", "рутина", "дела", "день", "сон", "расписание", "вечер", "утро")


# detect_message_type
def detect_message_type(user_message: str, current_state: CurrentState) -> str:
    lowered = " ".join(str(user_message or "").lower().strip().split())
    if any(marker in lowered for marker in _CORRECTION_MARKERS):
        return "correction"
    if current_state.pending_question and normalize_short_answer(lowered):
        return "short_answer"
    if lowered in _META_MESSAGES:
        return "meta_message"
    return "full_message"


def _detect_domain(lowered: str) -> str:
    if any(marker in lowered for marker in _HEALTH_MARKERS):
        return "health"
    if any(marker in lowered for marker in _ROUTINE_MARKERS):
        return "daily_routine"
    return "general"


def _detect_intent(lowered: str, message_type: str) -> str:
    if message_type == "correction":
        return "clarify"
    if any(marker in lowered for marker in _INFORM_MARKERS):
        return "inform"
    if any(marker in lowered for marker in _PLAN_MARKERS):
        return "plan"
    if any(marker in lowered for marker in _SUPPORT_MARKERS):
        return "support"
    return "support"


def _extract_goal(lowered: str, intent: str) -> str | None:
    if intent == "inform":
        return "получить объяснение"
    if intent == "plan":
        return "получить следующий шаг"
    if intent == "support":
        if "трев" in lowered or "страш" in lowered:
            return "снизить напряжение"
        if "сон" in lowered or "не спал" in lowered:
            return "разобраться с самочувствием"
        if "помоги" in lowered:
            return "получить поддержку"
    return None


def _detect_signals(lowered: str, domain: str, intent: str) -> list[str]:
    signals: list[str] = []
    if "трев" in lowered or "страш" in lowered:
        signals.append("distress")
    if "плохо" in lowered or "тяжело" in lowered or "не спал" in lowered:
        signals.append("emotional_pain")
    if "диализ" in lowered:
        signals.append("dialysis_context")
    if domain == "daily_routine":
        signals.append("routine_context")
    if intent == "inform":
        signals.append("needs_explanation")
    if intent == "plan":
        signals.append("needs_plan")
    return signals


def _detect_risk_flags(lowered: str, signals: list[str]) -> list[str]:
    risk_flags: list[str] = []
    if "перед диализ" in lowered:
        risk_flags.append("before_dialysis")
    if "не хочу жить" in lowered or "суиц" in lowered:
        risk_flags.append("critical_distress")
    if "болит" in lowered or "сильная боль" in lowered:
        risk_flags.append("medical_risk")
    if "distress" in signals:
        risk_flags.append("distress")
    return risk_flags


# classify_message
def classify_message(user_message: str, current_state: CurrentState) -> dict[str, Any]:
    lowered = " ".join(str(user_message or "").lower().strip().split())
    message_type = detect_message_type(lowered, current_state)
    domain = _detect_domain(lowered)
    intent = _detect_intent(lowered, message_type)
    signals = _detect_signals(lowered, domain, intent)
    risk_flags = _detect_risk_flags(lowered, signals)
    facts = ["mentioned_dialysis"] if "диализ" in lowered else []

    return {
        "message_type": message_type,
        "domain": domain,
        "intent": intent,
        "goal": _extract_goal(lowered, intent),
        "signals": signals,
        "risk_flags": risk_flags,
        "facts": facts,
    }
