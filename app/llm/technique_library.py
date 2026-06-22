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
    steps: tuple[str, ...] = ()
    completion_prompt: str = ""
    interactive: bool = False  # True = agent leads step-by-step; False = dump all steps at once
    therapeutic_intent: str = ""   # what the technique achieves at session level
    synthesis_hint: str = ""       # how to use collected patient responses for the final reframe


TECHNIQUE_LIBRARY: list[TechniqueCard] = [
    TechniqueCard(
        id="p01",
        name="Дыхание 4-7-8",
        tagline="Снять острый стресс за три минуты — прямо сейчас.",
        mechanism="удлинённый выдох (8 счётов) активирует парасимпатическую нервную систему, снижая ЧСС за 2–3 минуты",
        emotions=frozenset({"тревога", "стресс", "страх"}),
        arousal="высокое",
        dialysis_ok=True,
        steps=(
            "Устройтесь удобно — можно сидеть, можно лежать. Можно делать прямо на диализе.",
            "Закройте рот. Вдохните через нос, медленно считая до 4.",
            "Задержите дыхание на 7 счётов.",
            "Выдохните через рот со звуком на 8 счётов — как будто задуваете свечу.",
            "Это один цикл. Повторите 3–4 раза.",
            "После последнего выдоха — просто подышите обычно и заметьте, как изменилось тело.",
        ),
        completion_prompt="Как вы себя чувствуете после?",
        interactive=False,
    ),
    TechniqueCard(
        id="p02",
        name="Заземление 5-4-3-2-1",
        tagline="Вернуться в тело, когда эмоции накрыли.",
        mechanism="переключает внимание на сенсорный канал, прерывая петлю тревожных мыслей и возвращая контакт с реальностью",
        emotions=frozenset({"тревога", "страх", "стресс", "злость"}),
        arousal="высокое",
        dialysis_ok=True,
        steps=(
            "Оглянитесь вокруг. Назовите про себя 5 вещей, которые видите прямо сейчас.",
            "Прислушайтесь. Назовите 4 звука, которые слышите.",
            "Почувствуйте тело. Назовите 3 ощущения — кресло под спиной, одежда на коже, воздух.",
            "Сделайте вдох. Назовите 2 запаха — или просто почувствуйте воздух.",
            "Что сейчас во рту? Назовите 1 вкус.",
            "Сделайте медленный выдох. Вы здесь.",
        ),
        completion_prompt="Удалось вернуться в момент?",
        interactive=False,
    ),
    TechniqueCard(
        id="p03",
        name="Квадратное дыхание",
        tagline="Остановить нарастающую тревогу — незаметно для окружающих.",
        mechanism="ритмичный паттерн дыхания 4-4-4-4 стабилизирует вегетативную нервную систему",
        emotions=frozenset({"тревога", "стресс"}),
        arousal="среднее",
        dialysis_ok=True,
        steps=(
            "Можно делать с открытыми глазами — никто не заметит.",
            "Вдохните через нос на 4 счёта.",
            "Задержите дыхание на 4 счёта.",
            "Выдохните через нос на 4 счёта.",
            "Задержите на 4 счёта.",
            "Это один квадрат. Повторите 4–5 раз в своём темпе.",
        ),
        completion_prompt="Как вы себя чувствуете?",
        interactive=False,
    ),
    TechniqueCard(
        id="p04",
        name="Расслабление тела",
        tagline="Помочь телу отпустить напряжение и уснуть.",
        mechanism="последовательное напряжение-расслабление мышечных групп снимает хроническое мышечное напряжение",
        emotions=frozenset({"стресс", "тревога", "напряжение"}),
        arousal="среднее",
        dialysis_ok=False,
        steps=(
            "Лягте удобно. Закройте глаза.",
            "Напрягите ступни и икры на 5 секунд — сильно, как можете. Отпустите.",
            "Напрягите бёдра и живот на 5 секунд. Отпустите.",
            "Сожмите руки в кулаки и напрягите руки на 5 секунд. Отпустите.",
            "Поднимите плечи к ушам на 5 секунд. Отпустите.",
            "Зажмурьтесь и нахмурьтесь на 5 секунд. Отпустите.",
            "Почувствуйте, как тело стало тяжелее. Дышите спокойно.",
        ),
        completion_prompt="Тело расслабилось?",
        interactive=False,
    ),
    TechniqueCard(
        id="p05",
        name="Три варианта",
        tagline="Выйти из ступора, когда не знаешь что делать.",
        mechanism="структурирование хаоса в три конкретных пути снижает ощущение беспомощности и возвращает контроль",
        emotions=frozenset({"тревога", "растерянность", "стресс"}),
        arousal="низкое",
        dialysis_ok=True,
        steps=(
            "Назовите трудную ситуацию, которая давит прямо сейчас. Одним предложением.",
            "Первый вариант — самое очевидное, что приходит в голову. Что это?",
            "Второй вариант — самый маленький шаг, который реально сделать сегодня. Какой?",
            "Третий вариант — попросить кого-то помочь. Есть такой человек?",
            "Смотрите на три варианта. Какой кажется чуть менее тяжёлым?",
        ),
        completion_prompt="Появилась хоть одна идея что делать?",
        interactive=True,
    ),
    TechniqueCard(
        id="p06",
        name="Две минуты",
        tagline="Сдвинуться с места, когда нет сил начинать.",
        mechanism="микродействие запускает дофаминовую петлю «сделал → стало чуть лучше», снижая порог следующего шага",
        emotions=frozenset({"апатия", "усталость", "уныние"}),
        arousal="низкое",
        dialysis_ok=True,
        steps=(
            "Назовите одно дело, которое откладываете. Только одно.",
            "Поставьте таймер на 2 минуты — прямо сейчас.",
            "Делайте это дело ровно 2 минуты. Когда таймер звякнет — можете остановиться.",
            "Как прошло? Остановились или продолжили?",
        ),
        completion_prompt="Как вы себя чувствуете?",
        interactive=True,
    ),
    TechniqueCard(
        id="p07",
        name="Три дела на завтра",
        tagline="Разгрузить голову и почувствовать контроль над днём.",
        mechanism="экстернализация задач освобождает рабочую память, снижая когнитивную нагрузку и ощущение хаоса",
        emotions=frozenset({"тревога", "стресс", "рассеянность"}),
        arousal="низкое",
        dialysis_ok=True,
        steps=(
            "Возьмите телефон или листок.",
            "Напишите ровно три дела на завтра — не больше трёх.",
            "Если хочется написать больше — выберите три самых важных и остальное уберите.",
            "Отложите список до завтра.",
        ),
        completion_prompt="Стало немного легче?",
        interactive=False,
    ),
    TechniqueCard(
        id="p08",
        name="Физиологический вздох",
        tagline="Сбросить накопившееся напряжение за 30 секунд.",
        mechanism="двойной вдох раскрывает альвеолы; долгий выдох через рот — самый быстрый нейрорегуляторный отклик",
        emotions=frozenset({"стресс", "выгорание", "злость", "раздражение"}),
        arousal="высокое",
        dialysis_ok=True,
        steps=(
            "Сделайте обычный вдох через нос.",
            "В конце вдоха — добавьте ещё короткий вдох-добор через нос (как всхлип).",
            "Теперь медленно и долго выдохните через рот — как будто сдуваетесь.",
            "Повторите 2–3 раза. Это всё.",
        ),
        completion_prompt="Как вы себя чувствуете?",
        interactive=False,
    ),
    TechniqueCard(
        id="p09",
        name="Три вещи которые тело сделало сегодня",
        tagline="Заметить себя — не сквозь болезнь, а просто себя.",
        mechanism="нейтральное наблюдение за фактами без оценки ослабляет самокритику и восстанавливает ощущение ресурса",
        emotions=frozenset({"грусть", "апатия", "подавленность", "уныние"}),
        arousal="низкое",
        dialysis_ok=True,
        steps=(
            "Закройте глаза на секунду. Вспомните одно простое действие, которое ваше тело сделало сегодня — самое обычное, которое мы обычно не замечаем.",
            "Назовите ещё два-три таких действия. Самых простых — встал, поел, умылся, дошёл до диализа.",
            "Посмотрите на весь список. Что вы замечаете, когда видите всё это вместе?",
        ),
        completion_prompt="Что вы замечаете, глядя на всё это?",
        interactive=True,
        therapeutic_intent=(
            "Помочь пациенту заметить, что несмотря на усталость его тело активно работало — "
            "восстановить ощущение ресурса и снизить самокритику."
        ),
        synthesis_hint=(
            "Используй конкретные действия, которые пациент назвал, как доказательства его продуктивности. "
            "Нормализуй усталость после диализа как физиологическую норму, а не признак слабости. "
            "Подчеркни: то, что он перечислил — уже много для человека после 4+ часов процедуры. "
            "Регулярный диализ сам по себе — уже подвиг. Если пациент говорит «да... но устал» — "
            "признай «да» как реальный результат, а усталость — как закономерную цену этой работы."
        ),
    ),
    TechniqueCard(
        id="p10",
        name="Сжать и отпустить",
        tagline="Разрядить острую злость прямо в кресле — за одну минуту.",
        mechanism="острая мышечная нагрузка расходует адреналин; резкое расслабление запускает парасимпатический ответ",
        emotions=frozenset({"злость", "раздражение"}),
        arousal="высокое",
        dialysis_ok=True,
        steps=(
            "Сожмите обе руки в кулаки — как можно сильнее. Удерживайте 10 секунд.",
            "Резко разожмите. Почувствуйте, как напряжение уходит из рук.",
            "Поднимите плечи к ушам — сильно, на 10 секунд. Резко опустите. Выдохните.",
            "Если можно — напрягите бёдра и икры на 10 секунд. Отпустите.",
            "Сделайте три медленных выдоха. Просто подышите.",
        ),
        completion_prompt="Стало чуть легче в теле?",
        interactive=False,
    ),
    TechniqueCard(
        id="p11",
        name="Скажи себе то, что сказал бы другу",
        tagline="Отнестись к себе с той же добротой, что к близкому человеку.",
        mechanism="взгляд на себя со стороны активирует систему самоуспокоения, снижая руминацию через смягчение самокритики",
        emotions=frozenset({"грусть", "уныние", "одиночество", "подавленность"}),
        arousal="низкое",
        dialysis_ok=True,
        steps=(
            "Остановитесь. Что сейчас тяжело? Назовите это — хотя бы одним словом.",
            "Представьте: близкий вам человек переживает то же самое. Что бы вы ему сказали — по-человечески, с теплом?",
            "Скажите это себе — вслух или про себя. Если слова не идут — просто положите руку на грудь и посидите так минуту.",
        ),
        completion_prompt="Удалось сказать что-то доброе себе?",
        interactive=True,
        therapeutic_intent=(
            "Активировать самосострадание через смещение внутреннего диалога с самокритики на поддержку."
        ),
        synthesis_hint=(
            "Используй слова поддержки, которые пациент нашёл для воображаемого друга, и верни их ему самому. "
            "Если слова нашлись — отметь это как реальный навык, который он только что применил. "
            "Если было трудно подобрать слова — нормализуй: самосострадание требует практики, "
            "и то, что он попробовал — уже шаг. Тепло к себе не обязано приходить сразу."
        ),
    ),
    TechniqueCard(
        id="p12",
        name="Холодный якорь",
        tagline="Мгновенно вернуть себя в настоящее, когда охватывает страх.",
        mechanism="тактильный стимул переключает внимание с внутреннего симптома на сенсорный канал, прерывая страховой цикл",
        emotions=frozenset({"страх", "паника", "тревога"}),
        arousal="высокое",
        dialysis_ok=True,
        steps=(
            "Найдите что-то холодное или плотное рядом: стакан с водой, поручень кресла, собственная ладонь.",
            "Приложите к запястью или щеке. Просто почувствуйте — температуру, текстуру.",
            "Сделайте медленный выдох — длиннее вдоха.",
            "Назовите про себя 3 вещи, которые видите прямо сейчас.",
            "Напомните себе: «Я сейчас в безопасности. Это ощущение — не факт об опасности».",
        ),
        completion_prompt="Стало немного спокойнее?",
        interactive=False,
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
        raw_steps = row.instruction or []  # type: ignore[attr-defined]
        steps = tuple(str(s).strip() for s in raw_steps if str(s).strip())
        # Prefer static library's interactive flag — it's authoritative for known practices.
        # DB type column doesn't reliably encode step-by-step guidance intent.
        static_entry = next((c for c in TECHNIQUE_LIBRARY if c.id == short_id), None)
        if static_entry is not None:
            interactive = static_entry.interactive
        else:
            practice_type = str(getattr(row, "type", "") or "").lower()
            interactive = practice_type in {"cognitive", "behavioral"} and len(steps) > 1
        return TechniqueCard(
            id=short_id,
            name=row.title,  # type: ignore[attr-defined]
            tagline=row.tagline or "",  # type: ignore[attr-defined]
            mechanism=row.mechanism or "",  # type: ignore[attr-defined]
            emotions=frozenset(tags),
            arousal=row.arousal_level or "высокое",  # type: ignore[attr-defined]
            dialysis_ok=row.dialysis_ok if row.dialysis_ok is not None else True,  # type: ignore[attr-defined]
            steps=steps,
            completion_prompt=str(getattr(row, "completion_prompt", "") or "").strip(),
            interactive=interactive,
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


def get_technique_by_id(technique_id: str) -> TechniqueCard | None:
    # Static library is authoritative for known practices (curated steps and completion prompts).
    # Only fall back to DB cache for IDs not present in static library.
    for card in TECHNIQUE_LIBRARY:
        if card.id == technique_id:
            return card
    for card in _cache:
        if card.id == technique_id:
            return card
    return None


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


def _negated_emotion_stems(text: str) -> set[str]:
    """Return stems from _EMOTION_STEMS that are directly preceded by не/нет/без in text."""
    text_l = text.lower()
    negated: set[str] = set()
    for m in re.finditer(r'\b(не|нет|без)\s+(\w+)', text_l):
        neg_word = m.group(2)
        for emotion, stems in _EMOTION_STEMS.items():
            if any(stem in neg_word for stem in stems):
                negated.add(emotion)
    return negated


def infer_emotions(message: str, context: str = "") -> set[str]:
    """Return the set of canonical emotion names detected in message + context.

    Message takes priority: if the message explicitly names emotions, those are
    used and context is ignored (prevents old context from overriding corrections
    like «не тревогу, мне грустно»). Negated emotions (не/нет/без X) are excluded.
    """
    msg_lower = message.lower()
    negated = _negated_emotion_stems(message)

    # Check message first
    msg_found: set[str] = set()
    for emotion, stems in _EMOTION_STEMS.items():
        if emotion in negated:
            continue
        if any(stem in msg_lower for stem in stems):
            msg_found.add(emotion)

    # If message has clear emotion signals, use only those (don't mix in context)
    if msg_found:
        found = msg_found
    else:
        # Ambiguous / short message — fall back to message + context
        ctx_lower = context.lower()
        combined = f"{msg_lower} {ctx_lower}"
        found = set()
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
    exclude_ids: list[str] | None = None,
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

    _exclude: set[str] = set(filter(None, (exclude_ids or [])))
    if exclude_id:
        _exclude.add(exclude_id)

    candidates: list[tuple[int, TechniqueCard]] = []

    for card in _active_library():
        if card.id in _exclude:
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


def format_interactive_step(card: TechniqueCard, step_idx: int) -> str:
    """Inject a single step of an interactive technique for the expert prompt."""
    total = len(card.steps)
    step_text = card.steps[step_idx]
    return (
        f"[{card.id}] ИНТЕРАКТИВНЫЙ ШАГ ({step_idx + 1} из {total}):\n"
        f"«{step_text}»\n"
        f"Шаг сейчас ДОЛЖЕН передать пациенту ИМЕННО этот текст — не меняй суть, не придумывай свой вариант. "
        f"Допустимо только: адаптировать тон (ты/вы).\n"
        f"ОБЯЗАТЕЛЬНО: поле «Шаг сейчас» ДОЛЖНО начинаться с [{card.id}] — "
        f"без этого префикса прогресс техники не сохранится.\n"
        f"Правило: Режим интервенция, ИСКЛЮЧЕНИЕ-рефлексия НЕ применяется (техника ещё не завершена)."
    )


def format_technique_synthesis(card: TechniqueCard) -> str:
    """Adaptive completion block: synthesize using patient data or ask completion question."""
    prompt = card.completion_prompt or "Что заметил? Что почувствовал после?"
    intent = card.therapeutic_intent or ""
    hint = card.synthesis_hint or ""
    intent_line = f"Терапевтическая цель: {intent}\n" if intent else ""
    hint_line = f"Синтез-подсказка: {hint}\n" if hint else ""
    return (
        f"[{card.id}] ВСЕ ШАГИ ВЫПОЛНЕНЫ ({len(card.steps)} из {len(card.steps)}).\n"
        f"{intent_line}"
        f"{hint_line}"
        f"\n"
        f"ВЫБЕРИ ОДИН ИЗ ДВУХ ПУТЕЙ:\n"
        f"А. Если пациент уже дал обратную связь о состоянии (любое «да», «нет», «но...», «немного»):\n"
        f"   Оцени эффективность и выбери стратегию. Произведи синтез используя Синтез-подсказку выше.\n"
        f"   Если есть возражение («да... но...») — открой ветку: Ветка: открыть, Тип ветки: возражение.\n"
        f"Б. Если обратной связи о состоянии нет:\n"
        f"   Режим уточнить, Шаг сейчас: нет, Вопрос пациенту: «{prompt}»"
    )


def format_technique_completion(card: TechniqueCard) -> str:
    """Kept for backward compatibility — delegates to format_technique_synthesis."""
    return format_technique_synthesis(card)


def format_techniques_block(techniques: list[TechniqueCard], current_id: str | None = None) -> str:
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
        current_mark = " (текущая)" if t.id == current_id else ""
        if t.interactive:
            mode_note = f" · интерактивная ({len(t.steps)} шага — агент ведёт пошагово)"
        else:
            mode_note = ""
        entry = (
            f"[{t.id}] {t.name}{current_mark} · {t.arousal} возбуждение · {emotions_str}{dialysis_note}{mode_note}\n"
            f"  Механизм: {t.mechanism}"
        )
        if t.interactive and t.steps:
            first_step = t.steps[0]
            entry += (
                f"\n  Шаг 1 (выдай ИМЕННО этот текст в поле «Шаг сейчас», начни с [{t.id}]):\n"
                f"  «{first_step}»"
            )
        elif not t.interactive and t.steps:
            steps_text = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(t.steps))
            entry += f"\n  Шаги (выдай все сразу в Шаг сейчас):\n{steps_text}"
        lines.append(entry)
    return "\n".join(lines)
