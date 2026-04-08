from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.llm.router import RequestType, RouterResult


@dataclass(slots=True)
class IntakeProblem:
    code: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class HelpIntakeResult:
    message_kind: str
    is_help_request: bool
    problems: list[IntakeProblem] = field(default_factory=list)
    primary_problem: str | None = None
    patient_intent: str | None = None
    context_factors: list[str] = field(default_factory=list)
    information_sufficient: bool = True
    clarification_needed: bool = False
    clarification_reason: str | None = None
    suggested_question: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["problems"] = [item.to_dict() for item in self.problems]
        return payload


_HELP_MARKERS = (
    "помоги",
    "помочь",
    "что делать",
    "как справиться",
    "как пережить",
    "что со мной",
    "не понимаю",
    "тревожно",
    "мне плохо",
    "не знаю",
)

_EXPLANATION_MARKERS = (
    "почему",
    "что это",
    "объясни",
    "объяснить",
    "что со мной",
    "нормально ли",
    "понять",
)

_EDUCATION_MARKERS = (
    "что почитать",
    "какой урок",
    "урок",
    "материал",
    "практик",
)

_PRACTICAL_MARKERS = (
    "что делать сегодня",
    "как прожить день",
    "пережить день",
    "на ближайшие часы",
    "как действовать",
)

_SLEEP_MARKERS = (
    "уснуть",
    "сон",
    "спал",
    "сплю",
    "бессон",
    "ночь",
)

_EMOTIONAL_MARKERS = (
    "трев",
    "страшно",
    "страх",
    "напряж",
    "паник",
    "пережива",
    "эмоци",
)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _detect_message_kind(text: str, router_result: RouterResult) -> str:
    if router_result.request_type == RequestType.QUICK_ACTION:
        return "quick_action"
    lower = text.lower()
    if _contains_any(lower, _EDUCATION_MARKERS):
        return "content_request"
    if lower.startswith("можно ") or lower.endswith("?"):
        return "specific_question"
    if router_result.request_type in {RequestType.EMOTIONAL, RequestType.CLINICAL} or _contains_any(lower, _HELP_MARKERS):
        return "help_request"
    return "general_message"


def analyze_help_intake(
    *,
    user_input: str,
    router_result: RouterResult,
    parser_mood: str | None,
    parser_domain_hints: list[str] | None,
) -> HelpIntakeResult:
    lower = " ".join(str(user_input or "").lower().split())
    hints = set(parser_domain_hints or [])
    message_kind = _detect_message_kind(lower, router_result)
    is_help_request = message_kind == "help_request"

    problems: list[IntakeProblem] = []
    context_factors: list[str] = []

    def add_problem(code: str, evidence: str) -> None:
        if any(item.code == code for item in problems):
            return
        problems.append(IntakeProblem(code=code, evidence=[evidence]))

    if "sleep" in hints or _contains_any(lower, _SLEEP_MARKERS):
        add_problem("sleep_problem", "sleep_signal")
    if "emotion" in hints or _contains_any(lower, _EMOTIONAL_MARKERS) or parser_mood == "bad":
        add_problem("emotional_distress", "emotion_signal")
    if any(token in lower for token in ("разбит", "устал", "нет сил", "сил мало", "слабость")):
        add_problem("low_energy", "energy_signal")
    if router_result.request_type == RequestType.CLINICAL:
        add_problem("clinical_symptom", "clinical_request")

    if "перед диализ" in lower:
        context_factors.append("before_dialysis")
    if "после диализ" in lower:
        context_factors.append("after_dialysis")
    if "сегодня" in lower:
        context_factors.append("today")
    if any(token in lower for token in ("несколько дней", "уже дни", "последние дни", "неделю", "несколько ночей")):
        context_factors.append("ongoing_pattern")
    if any(token in lower for token in ("ночью", "ночь", "прошлой ночью", "после плохой ночи")):
        context_factors.append("night_context")

    patient_intent: str | None = None
    if _contains_any(lower, _EDUCATION_MARKERS):
        patient_intent = "education_material"
    elif _contains_any(lower, _EXPLANATION_MARKERS):
        patient_intent = "explanation"
    elif _contains_any(lower, _PRACTICAL_MARKERS):
        patient_intent = "practical_day_support"
    elif any(token in lower for token in ("уснуть", "наладить сон", "помочь со сном")):
        patient_intent = "sleep_support"
    elif router_result.request_type == RequestType.EMOTIONAL or _contains_any(lower, ("хочу справиться", "как справиться", "поддерж", "успоко", "помоги")):
        patient_intent = "emotional_support"

    primary_problem = problems[0].code if problems else None

    if not is_help_request:
        return HelpIntakeResult(
            message_kind=message_kind,
            is_help_request=False,
            problems=problems,
            primary_problem=primary_problem,
            patient_intent=patient_intent,
            context_factors=context_factors,
            information_sufficient=True,
            clarification_needed=False,
        )

    information_sufficient = True
    clarification_needed = False
    clarification_reason: str | None = None
    suggested_question: str | None = None

    if not problems:
        information_sufficient = False
        clarification_needed = True
        clarification_reason = "no_clear_problem"
        suggested_question = "Что сейчас беспокоит тебя больше всего?"
    elif not patient_intent and len(problems) > 1:
        information_sufficient = False
        clarification_needed = True
        clarification_reason = "multiple_problems_unclear_intent"
        suggested_question = "Что тебе сейчас важнее: поддержка, помощь прожить день или объяснение, что происходит?"
    elif not patient_intent and problems:
        # один явный фокус допускаем без уточнения, но помечаем как inferred
        if primary_problem == "sleep_problem":
            patient_intent = "sleep_support"
        elif primary_problem == "emotional_distress":
            patient_intent = "emotional_support"
        elif primary_problem == "low_energy":
            patient_intent = "practical_day_support"

    return HelpIntakeResult(
        message_kind=message_kind,
        is_help_request=True,
        problems=problems,
        primary_problem=primary_problem,
        patient_intent=patient_intent,
        context_factors=context_factors,
        information_sufficient=information_sufficient,
        clarification_needed=clarification_needed,
        clarification_reason=clarification_reason,
        suggested_question=suggested_question,
    )
