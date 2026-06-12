"""Technique library for the emotional expert.

Prescribes which technique to use; LLM frames the mechanism explanation.
At startup, the cache is loaded from practices.practices (DB); the static
TECHNIQUE_LIBRARY below is the seed / fallback for tests and dev mode.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("gpt-support-llm.technique_library")


@dataclass(frozen=True, slots=True)
class TechniqueCard:
    id: str
    name: str
    tagline: str
    mechanism: str
    emotions: frozenset[str]
    arousal: str  # высокое | среднее | низкое
    dialysis_ok: bool


TECHNIQUE_LIBRARY: list[TechniqueCard] = [
    TechniqueCard(
        id="p01",
        name="Дыхание 4-7-8",
        tagline="Снять острый стресс за три минуты — прямо сейчас.",
        mechanism="удлинённый выдох (8 счётов) активирует парасимпатическую нервную систему, снижая ЧСС за 2–3 минуты",
        emotions=frozenset({"тревога", "стресс", "страх"}),
        arousal="высокое",
        dialysis_ok=True,
    ),
    TechniqueCard(
        id="p02",
        name="Заземление 5-4-3-2-1",
        tagline="Вернуться в тело, когда эмоции накрыли.",
        mechanism="переключает внимание на сенсорный канал, прерывая петлю тревожных мыслей и возвращая контакт с реальностью",
        emotions=frozenset({"тревога", "страх", "стресс", "злость"}),
        arousal="высокое",
        dialysis_ok=True,
    ),
    TechniqueCard(
        id="p03",
        name="Квадратное дыхание",
        tagline="Остановить нарастающую тревогу — незаметно для окружающих.",
        mechanism="ритмичный паттерн дыхания 4-4-4-4 стабилизирует вегетативную нервную систему",
        emotions=frozenset({"тревога", "стресс"}),
        arousal="среднее",
        dialysis_ok=True,
    ),
    TechniqueCard(
        id="p04",
        name="Расслабление тела",
        tagline="Помочь телу отпустить напряжение и уснуть.",
        mechanism="последовательное напряжение-расслабление мышечных групп снимает хроническое мышечное напряжение",
        emotions=frozenset({"стресс", "тревога", "напряжение"}),
        arousal="среднее",
        dialysis_ok=False,
    ),
    TechniqueCard(
        id="p05",
        name="Три варианта",
        tagline="Выйти из ступора, когда не знаешь что делать.",
        mechanism="структурирование хаоса в три конкретных пути снижает ощущение беспомощности и возвращает контроль",
        emotions=frozenset({"тревога", "растерянность", "стресс"}),
        arousal="низкое",
        dialysis_ok=True,
    ),
    TechniqueCard(
        id="p06",
        name="Две минуты",
        tagline="Сдвинуться с места, когда нет сил начинать.",
        mechanism="микродействие запускает дофаминовую петлю «сделал → стало чуть лучше», снижая порог следующего шага",
        emotions=frozenset({"апатия", "усталость", "уныние"}),
        arousal="низкое",
        dialysis_ok=True,
    ),
    TechniqueCard(
        id="p07",
        name="Три дела на завтра",
        tagline="Разгрузить голову и почувствовать контроль над днём.",
        mechanism="экстернализация задач освобождает рабочую память, снижая когнитивную нагрузку и ощущение хаоса",
        emotions=frozenset({"тревога", "стресс", "рассеянность"}),
        arousal="низкое",
        dialysis_ok=True,
    ),
    TechniqueCard(
        id="p08",
        name="Физиологический вздох",
        tagline="Сбросить накопившееся напряжение за 30 секунд.",
        mechanism="двойной вдох раскрывает альвеолы; долгий выдох через рот — самый быстрый нейрорегуляторный отклик",
        emotions=frozenset({"стресс", "выгорание", "злость", "раздражение"}),
        arousal="высокое",
        dialysis_ok=True,
    ),
    TechniqueCard(
        id="p09",
        name="Три вещи которые тело сделало сегодня",
        tagline="Заметить себя — не сквозь болезнь, а просто себя.",
        mechanism="нейтральное наблюдение за фактами без оценки ослабляет самокритику и восстанавливает ощущение ресурса",
        emotions=frozenset({"грусть", "апатия", "подавленность", "уныние"}),
        arousal="низкое",
        dialysis_ok=True,
    ),
    TechniqueCard(
        id="p10",
        name="Сжать и отпустить",
        tagline="Разрядить острую злость прямо в кресле — за одну минуту.",
        mechanism="острая мышечная нагрузка расходует адреналин; резкое расслабление запускает парасимпатический ответ",
        emotions=frozenset({"злость", "раздражение"}),
        arousal="высокое",
        dialysis_ok=True,
    ),
    TechniqueCard(
        id="p11",
        name="Скажи себе то, что сказал бы другу",
        tagline="Отнестись к себе с той же добротой, что к близкому человеку.",
        mechanism="взгляд на себя со стороны активирует систему самоуспокоения, снижая руминацию через смягчение самокритики",
        emotions=frozenset({"грусть", "уныние", "одиночество", "подавленность"}),
        arousal="низкое",
        dialysis_ok=True,
    ),
    TechniqueCard(
        id="p12",
        name="Холодный якорь",
        tagline="Мгновенно вернуть себя в настоящее, когда охватывает страх.",
        mechanism="тактильный стимул переключает внимание с внутреннего симптома на сенсорный канал, прерывая страховой цикл",
        emotions=frozenset({"страх", "паника", "тревога"}),
        arousal="высокое",
        dialysis_ok=True,
    ),
]

# ---------------------------------------------------------------------------
# DB-backed runtime cache (populated on startup via refresh_technique_cache)
# Falls back to TECHNIQUE_LIBRARY if cache is empty (dev / test / no DB)
# ---------------------------------------------------------------------------

_cache: list[TechniqueCard] = []

_PRACTICE_ID_RE = re.compile(r"^(p\d+)")


def _row_to_card(row: object) -> TechniqueCard | None:
    """Convert a DB row (or dict) to TechniqueCard, return None on bad data."""
    try:
        raw_id: str = row.id  # type: ignore[attr-defined]
        m = _PRACTICE_ID_RE.match(raw_id)
        if not m:
            return None
        short_id = m.group(1)
        tags = row.emotion_tags or []  # type: ignore[attr-defined]
        return TechniqueCard(
            id=short_id,
            name=row.title,  # type: ignore[attr-defined]
            tagline=row.tagline or "",  # type: ignore[attr-defined]
            mechanism=row.mechanism or "",  # type: ignore[attr-defined]
            emotions=frozenset(tags),
            arousal=row.arousal_level or "высокое",  # type: ignore[attr-defined]
            dialysis_ok=row.dialysis_ok if row.dialysis_ok is not None else True,  # type: ignore[attr-defined]
        )
    except Exception:
        return None


async def refresh_technique_cache() -> int:
    """Load active practices with technique metadata from DB into the in-memory cache.

    Returns the number of loaded cards. Leaves cache unchanged on failure.
    """
    try:
        from sqlalchemy import select
        from core.db.engine import async_session_maker
        from app.practices.models import StandalonePractice

        async with async_session_maker() as session:
            rows = (await session.scalars(
                select(StandalonePractice).where(
                    StandalonePractice.is_active.is_(True),
                    StandalonePractice.emotion_tags.is_not(None),
                ).order_by(StandalonePractice.id)
            )).all()

        cards = [c for row in rows if (c := _row_to_card(row)) is not None]
        if cards:
            _cache.clear()
            _cache.extend(cards)
            logger.info("technique_cache loaded %d cards from DB", len(cards))
        else:
            logger.warning("technique_cache: no cards from DB, retaining static fallback")
        return len(cards)
    except Exception as exc:
        logger.warning("technique_cache: DB load failed (%s), using static fallback", exc)
        return 0


def _active_library() -> list[TechniqueCard]:
    return _cache if _cache else TECHNIQUE_LIBRARY


# ---------------------------------------------------------------------------
# Emotion vocabulary — maps canonical emotion names to detection stems
# ---------------------------------------------------------------------------

_EMOTION_STEMS: dict[str, tuple[str, ...]] = {
    "тревога": ("тревог", "тревожн", "волнени", "беспокой", "нервнич"),
    "страх": ("страх", "страшн", "боюсь", "боится", "пугает", "напуган"),
    "злость": ("злост", "злюсь", "злой", "злится", "бешусь", "ненавиж", "достал", "достало"),
    "раздражение": ("раздраж", "раздражен", "бесит", "бесюсь", "бесит"),
    "грусть": ("грустн", "грусть", "уныни", "унылый", "тоск", "печал", "подавлен"),
    "апатия": ("апати", "устал", "нет сил", "нет желани"),
    "стресс": ("стресс", "напряжен", "давит"),
    "паника": ("паник", "паническ"),
    "усталость": ("устал", "усталост", "измотал", "истощен"),
    "одиночество": ("одиноч", "одинок", "никому", "не нужен", "не нужна"),
}

# ---------------------------------------------------------------------------
# Arousal vocabulary
# ---------------------------------------------------------------------------

_HIGH_AROUSAL_STEMS = (
    "паник", "паническ",
    "ужас", "невыносим",
    "колотит", "задыхаюсь", "задыхаться",
    "трясет", "трясёт", "трясусь", "дрожу", "дрожит",
    "бешусь", "ненавиж",
    "помогите", "спасите",
)

_HIGH_AROUSAL_INTENSIFIERS = (
    "очень сильно", "безумно", "жутко", "ужасно", "невыносимо",
)

_LOW_AROUSAL_STEMS = (
    "немного", "слегка", "чуть", "чуть-чуть",
    "слабо", "не очень", "не сильно", "слабенько",
    "устал", "устала", "усталост", "нет сил",
    "апати", "унылый", "тоск", "тяжело на душе",
)

# Explicit minimizers that on their own signal low arousal (absent high markers)
_EXPLICIT_MINIMIZERS = ("немного", "слегка", "чуть", "слабо", "не очень", "не сильно")


def infer_arousal(message: str, context: str = "") -> str:
    """Return 'высокое', 'среднее', or 'низкое' without any LLM call."""
    combined = f"{message} {context}".lower()

    # Formatting signals: CAPS words or multiple punctuation
    caps_words = len(re.findall(r'\b[А-ЯA-Z]{3,}\b', message))
    exclamations = message.count('!') + message.count('?')

    has_high_marker = any(stem in combined for stem in _HIGH_AROUSAL_STEMS)
    has_intensifier = any(p in combined for p in _HIGH_AROUSAL_INTENSIFIERS)
    has_formatting = caps_words >= 2 or exclamations >= 3

    # Explicit minimizers without any high signals → low arousal
    if not has_high_marker and not has_formatting and not has_intensifier:
        if any(m in combined for m in _EXPLICIT_MINIMIZERS):
            return "низкое"

    high_score = 0
    low_score = 0

    for stem in _HIGH_AROUSAL_STEMS:
        if stem in combined:
            high_score += 2
    for phrase in _HIGH_AROUSAL_INTENSIFIERS:
        if phrase in combined:
            high_score += 1
    if has_formatting:
        high_score += 2
    for stem in _LOW_AROUSAL_STEMS:
        if stem in combined:
            low_score += 1

    # Any low advantage (without high markers) → low arousal
    if low_score > high_score:
        return "низкое"
    if high_score >= low_score + 2:
        return "высокое"
    # Default: высокое — safer to over-respond than under-respond
    return "высокое"


def infer_emotions(message: str, context: str = "") -> set[str]:
    """Return the set of canonical emotion names detected in message + context."""
    combined = f"{message} {context}".lower()
    found: set[str] = set()
    for emotion, stems in _EMOTION_STEMS.items():
        if any(stem in combined for stem in stems):
            found.add(emotion)
    # паника implies страх
    if "паника" in found:
        found.add("страх")
    # раздражение implies злость
    if "раздражение" in found:
        found.add("злость")
    return found


def get_techniques(
    emotions: set[str],
    arousal: str,
    *,
    exclude_id: str | None = None,
    dialysis_ok: bool | None = None,
    max_results: int = 3,
) -> list[TechniqueCard]:
    """Return up to max_results techniques ranked by relevance.

    Matching rules (in priority order):
    1. Emotion intersection + exact arousal match
    2. Emotion intersection + adjacent arousal (±1 level)
    3. Fallback: best arousal match without emotion constraint
    """
    _AROUSAL_ORDER = {"высокое": 2, "среднее": 1, "низкое": 0}
    target_level = _AROUSAL_ORDER.get(arousal, 2)

    candidates: list[tuple[int, TechniqueCard]] = []

    for card in _active_library():
        if card.id == exclude_id:
            continue
        if dialysis_ok is True and not card.dialysis_ok:
            continue

        emotion_match = bool(card.emotions & emotions) if emotions else False
        card_level = _AROUSAL_ORDER.get(card.arousal, 2)
        arousal_distance = abs(card_level - target_level)

        # Priority score: higher is better
        # emotion match: +10, exact arousal: +4, adjacent: +2, off: 0
        score = 0
        if emotion_match:
            score += 10
        if arousal_distance == 0:
            score += 4
        elif arousal_distance == 1:
            score += 2

        candidates.append((score, card))

    # Sort by score descending, then by ID (deterministic)
    candidates.sort(key=lambda x: (-x[0], x[1].id))

    # Must have at least some relevance (score > 0) unless we have no options
    relevant = [c for _, c in candidates if _ > 0]
    if not relevant:
        relevant = [c for _, c in candidates]

    return relevant[:max_results]


def format_techniques_block(techniques: list[TechniqueCard]) -> str:
    """Format technique cards for injection into the expert user prompt."""
    if not techniques:
        return ""
    lines = [
        "Доступные техники для этой ситуации (режим интервенция: используй ТОЛЬКО одну из них, "
        "укажи id в начале поля Шаг сейчас — например '[p01] ...'):"
    ]
    for t in techniques:
        emotions_str = ", ".join(sorted(t.emotions))
        dialysis_note = "" if t.dialysis_ok else " · только вне диализа"
        lines.append(
            f"[{t.id}] {t.name} · {t.arousal} возбуждение · {emotions_str}{dialysis_note}\n"
            f"  Механизм: {t.mechanism}"
        )
    return "\n".join(lines)
