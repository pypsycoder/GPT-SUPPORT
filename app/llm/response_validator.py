from __future__ import annotations

from dataclasses import dataclass
import re


HYDRATION_PHRASES = (
    "пить больше воды",
    "пить воду",
    "пить больше жидкости",
    "пить жидкость",
    "восполнять жидкость",
    "hydrated",
)

HYDRATION_WORD_STEMS = (
    "гидрат",
)

FOOD_PHRASES = (
    "что съесть",
    "что выпить",
    "тяжелой еды",
    "легкую пищу",
    "легкая пища",
    "напитков с кофеином",
    "напитки с кофеином",
    "травяной чай",
)

FOOD_WORDS = (
    "перекус",
    "перекуси",
    "перекусить",
    "поесть",
    "поешь",
    "кушать",
    "кушай",
    "кофеин",
    "кофе",
    "чай",
    "напиток",
    "напитки",
    "суп",
    "йогурт",
    "кефир",
    "фрукты",
    "еда",
    "пища",
)

FOOD_WORD_STEMS = (
    "ромашк",
    "мятн",
)

TEMPLATE_REASSURANCE_PATTERNS = (
    "ты справишься",
    "держись",
    "всё будет хорошо",
    "все будет хорошо",
    "не переживай",
)

DOCTOR_ESCALATION_PATTERNS = (
    "обратись к врачу",
    "обратитесь к врачу",
    "обратиться к врачу",
    "обратись к медсестре",
    "обратиться к медсестре",
    "расскажи врачу",
    "расскажи медсестре",
    "поговори с врачом",
    "поговори с медсестрой",
    "сообщи врачу",
    "сообщи медсестре",
    "сообщи медицинскому персоналу",
    "обратиться за консультацией",
    "обратиться за консультацией к врачу",
)

CARE_TEAM_ASSUMPTION_PATTERNS = (
    "медсестра поможет",
    "врач поможет",
    "они помогут",
    "точно помогут",
    "они подскажут",
    "подскажут, что делать",
    "они знают, как помочь",
    "они умеют помогать",
    "они знают, что делать",
    "тебе помогут",
)

ACTION_PATTERNS = (
    "попробуй",
    "сделай",
    "отдохни",
    "снизь",
    "замедлись",
    "подыши",
    "закрой глаза",
    "сделай паузу",
    "отложи",
    "избегай",
    "постарайся",
    "выбери",
    "найди",
    "используй",
    "ограни",
    "запиши",
    "сообщи",
    "обсуди",
    "скажи",
    "поговори",
    "обратись",
    "поешь",
    "поесть",
    "выпей",
    "выпить",
)

ACTION_WORD_STEMS = (
    "созда",
    "убер",
    "постара",
)


@dataclass(slots=True)
class ValidationResult:
    triggered: bool
    reasons: list[str]


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in patterns)


def _contains_word(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words)


def _contains_word_stem(text: str, stems: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(stem)}\w*", lowered) for stem in stems)


def _contains_hydration_advice(text: str) -> bool:
    return _contains_any(text, HYDRATION_PHRASES) or _contains_word_stem(text, HYDRATION_WORD_STEMS)


def _contains_food_advice(text: str) -> bool:
    return (
        _contains_any(text, FOOD_PHRASES)
        or _contains_word(text, FOOD_WORDS)
        or _contains_word_stem(text, FOOD_WORD_STEMS)
    )


def _has_action_step(text: str) -> bool:
    return _contains_any(text, ACTION_PATTERNS) or _contains_word_stem(text, ACTION_WORD_STEMS)


def _has_early_escalation(text: str, patterns: tuple[str, ...], *, window: int = 3) -> bool:
    lines = [line.strip(" -\t").lower() for line in text.splitlines() if line.strip()]
    for line in lines[:window]:
        if any(pattern in line for pattern in patterns):
            return True
    return False


def validate_response_for_rewrite(
    response_text: str,
    *,
    allow_validation_only: bool = False,
) -> ValidationResult:
    reasons: list[str] = []

    if _contains_hydration_advice(response_text):
        reasons.append("hydration_advice")
    if _contains_food_advice(response_text):
        reasons.append("food_advice")
    if _contains_any(response_text, TEMPLATE_REASSURANCE_PATTERNS):
        reasons.append("template_reassurance")
    if _has_early_escalation(response_text, DOCTOR_ESCALATION_PATTERNS):
        reasons.append("early_escalation")
    if _contains_any(response_text, CARE_TEAM_ASSUMPTION_PATTERNS):
        reasons.append("care_team_assumption")
    if not allow_validation_only and not _has_action_step(response_text):
        reasons.append("no_action_step")

    return ValidationResult(triggered=bool(reasons), reasons=reasons)
