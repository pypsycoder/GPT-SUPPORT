"""
Трёхуровневый роутер: детерминизм -> эмбеддинги -> LLM.

Проблема текущего роутера в GPT-SUPPORT: `any(kw in lower for kw in KEYWORDS)`.
Это подстрочное вхождение по спискам слов. Оно:
  * ловит «покончить с этим делом» как SAFETY;
  * не ловит «больше не хочу так жить», если такой фразы нет в списке;
  * требует ручного расширения списков — те самые «правила и костыли».

Правильная схема — каскад, где каждый следующий уровень дороже предыдущего
и вызывается только если предыдущий не дал уверенного ответа:

    L0  детерминированные сигналы   0 токенов, ~0 мс   — кнопки, числа, команды
    L1  kNN по эмбеддингам          ~1 эмбеддинг       — 90% текстовых запросов
    L2  LLM-классификатор (Lite)    ~200 токенов       — только неуверенные случаи

Важно про L0 и безопасность: списки стоп-слов остаются, но работают
ТОЛЬКО на повышение приоритета (recall), никогда на понижение.
Ложноположительный SAFETY стоит одного лишнего аккуратного ответа.
Ложноотрицательный стоит несопоставимо дороже.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Sequence

from pydantic import BaseModel, Field

from gigachat_client import GigaChatClient


class Intent(StrEnum):
    SMALLTALK = "smalltalk"          # приветствие, благодарность
    EMOTIONAL = "emotional"          # эмоциональная поддержка
    SELFCARE = "selfcare"            # режим, питание, вода, сон
    CLINICAL = "clinical"            # симптомы, показатели
    EDUCATION = "education"          # запрос на обучение
    LOGISTICS = "logistics"          # расписание, организационное
    SAFETY = "safety"                # кризис
    OFFTOPIC = "offtopic"


# Какие инструменты давать модели при каком интенте.
# Это и есть главный рычаг экономии: описания функций стоят токенов.
TOOLS_BY_INTENT: dict[Intent, list[str]] = {
    Intent.SMALLTALK: [],
    Intent.EMOTIONAL: [],
    Intent.SELFCARE: ["get_dialysis_schedule", "search_education"],
    Intent.CLINICAL: ["get_recent_vitals", "get_dialysis_schedule"],
    Intent.EDUCATION: ["search_education"],
    Intent.LOGISTICS: ["get_dialysis_schedule"],
    Intent.SAFETY: [],
    Intent.OFFTOPIC: [],
}

MODEL_BY_INTENT: dict[Intent, str] = {
    Intent.SMALLTALK: "GigaChat-2",
    Intent.EMOTIONAL: "GigaChat-2-Pro",
    Intent.SELFCARE: "GigaChat-2-Pro",
    Intent.CLINICAL: "GigaChat-2-Pro",
    Intent.EDUCATION: "GigaChat-2",
    Intent.LOGISTICS: "GigaChat-2",
    Intent.SAFETY: "GigaChat-2-Max",
    Intent.OFFTOPIC: "GigaChat-2",
}


@dataclass(slots=True)
class Route:
    intent: Intent
    confidence: float
    level: Literal["L0", "L1", "L2"]
    tools: list[str]
    model: str
    tokens_spent: int = 0


# --------------------------------------------------------------------------- #
# L0 — детерминированные сигналы
# --------------------------------------------------------------------------- #

# Пациенты пишут АД тремя способами: «160/100», «160 на 100», «160-100».
# Твой нынешний _is_emergency_vitals ловит любое трёхзначное число (\d{3,}),
# то есть «выпил 250 мл» становится гипертоническим кризом. Здесь — пара чисел.
_BP_RE = re.compile(r"\b(\d{2,3})\s*(?:[/\\-]|\bна\b)\s*(\d{2,3})\b", re.IGNORECASE)

# Только recall-сигналы. Совпало — эскалируем, не совпало — ничего не значит.
#
# Формулировки собраны так, чтобы ловить перефразировки вокруг одного корня:
# «смысл», «жить», «терпеть». Это компромисс: «не вижу смысла в этом упражнении»
# тоже сработает. Ложноположительный SAFETY стоит одного лишнего аккуратного
# ответа, ложноотрицательный — несопоставимо дороже. Список расширяйте из
# реальных логов, но НИКОГДА не сужайте ради точности.
_SAFETY_PATTERNS = (
    r"не\s+хочу\s+(больше\s+)?жить",
    r"не\s+вижу\s+смысла",
    r"нет\s+смысла\s+(жить|продолжать|лечиться|в\s+лечении)",
    r"незачем\s+(жить|продолжать)",
    r"покончи\w*\s+с\s+соб",
    r"суицид",
    r"убить\s+себя",
    r"свести\s+счёты\s+с\s+жизнью",
    r"лучше\s+бы\s+(я\s+)?умер",
    r"хочу\s+умереть",
    r"больше\s+не\s+могу\s+(терпеть|это\s+выносить)",
    r"хочу,?\s+чтобы\s+(это|всё)\s+закончилось",
    # чередование основы: брос-ить / брош-у, поэтому оба варианта явно
    r"(брос\w*|брош\w*|прекра\w+|отказ\w*)\s+(от\s+)?(диализ|лечени|сеанс)",
)
_SAFETY_RE = re.compile("|".join(_SAFETY_PATTERNS), re.IGNORECASE)


def route_l0(text: str, source: str) -> Route | None:
    """Возвращает Route, только если уверен на 100%. Иначе None."""
    if source == "button":
        return Route(Intent.LOGISTICS, 1.0, "L0", TOOLS_BY_INTENT[Intent.LOGISTICS],
                     MODEL_BY_INTENT[Intent.LOGISTICS])

    if _SAFETY_RE.search(text):
        return Route(Intent.SAFETY, 1.0, "L0", [], MODEL_BY_INTENT[Intent.SAFETY])

    # Гипертонический криз по числам — детерминированный клинический триггер.
    for sys_bp, dia_bp in _BP_RE.findall(text):
        if int(sys_bp) >= 180 or int(dia_bp) >= 110:
            return Route(Intent.CLINICAL, 1.0, "L0",
                         TOOLS_BY_INTENT[Intent.CLINICAL], "GigaChat-2-Max")

    if len(text.strip()) <= 3:
        return Route(Intent.SMALLTALK, 1.0, "L0", [], MODEL_BY_INTENT[Intent.SMALLTALK])

    return None


# --------------------------------------------------------------------------- #
# L1 — kNN по эмбеддингам
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class Prototype:
    """Размеченный пример. 15-30 штук на интент — рабочий минимум."""
    text: str
    intent: Intent
    vector: list[float] | None = None


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class EmbeddingRouter:
    """
    kNN по прототипам.

    Почему это лучше ключевых слов:
      * ловит перефразировки, которых нет в списках;
      * расширяется добавлением примеров, а не правкой регулярок;
      * даёт калиброванную уверенность, по которой видно, когда звать L2.

    Прототипы эмбеддятся один раз при старте и кэшируются.
    Эмбеддинг запроса — один дешёвый вызов (не chat).
    """

    def __init__(self, client: GigaChatClient, prototypes: list[Prototype],
                 *, model: str = "EmbeddingsGigaR", threshold: float = 0.62,
                 margin: float = 0.05, k: int = 5) -> None:
        self.client = client
        self.prototypes = prototypes
        self.model = model
        self.threshold = threshold   # ниже — не доверяем
        self.margin = margin         # разрыв между 1-м и 2-м интентом
        self.k = k
        self._ready = False

    async def warmup(self) -> None:
        missing = [p for p in self.prototypes if p.vector is None]
        if not missing:
            self._ready = True
            return
        vectors = await self.client.embeddings([p.text for p in missing], model=self.model)
        for proto, vec in zip(missing, vectors):
            proto.vector = vec
        self._ready = True

    async def route(self, text: str) -> Route | None:
        if not self._ready:
            await self.warmup()
        query = (await self.client.embeddings([text], model=self.model))[0]

        scored = sorted(
            ((cosine(query, p.vector or []), p) for p in self.prototypes),
            key=lambda x: x[0], reverse=True,
        )[: self.k]
        if not scored:
            return None

        # Голосование с весами: сглаживает единичный шумный прототип.
        votes: dict[Intent, float] = {}
        for score, proto in scored:
            votes[proto.intent] = votes.get(proto.intent, 0.0) + score

        ranked = sorted(votes.items(), key=lambda x: x[1], reverse=True)
        best_intent, best_score = ranked[0]
        top_sim = scored[0][0]

        if top_sim < self.threshold:
            return None
        if len(ranked) > 1 and (best_score - ranked[1][1]) / best_score < self.margin:
            return None   # два интента слишком близко — пусть решает L2

        return Route(best_intent, round(top_sim, 3), "L1",
                     TOOLS_BY_INTENT[best_intent], MODEL_BY_INTENT[best_intent])


# --------------------------------------------------------------------------- #
# L2 — LLM-классификатор
# --------------------------------------------------------------------------- #

class IntentDecision(BaseModel):
    intent: Literal[
        "smalltalk", "emotional", "selfcare", "clinical",
        "education", "logistics", "safety", "offtopic",
    ]
    confidence: float = Field(ge=0.0, le=1.0)


CLASSIFIER_SYSTEM = """Ты классификатор запросов пациента на программном гемодиализе.
Верни ровно один интент.

smalltalk — приветствие, благодарность, светская фраза
emotional — переживания, тревога, подавленность, одиночество, злость
selfcare  — режим дня, питание, водный баланс, сон, активность
clinical  — симптомы, показатели, лекарства, самочувствие после сеанса
education — просьба объяснить, научить, дать материал
logistics — расписание, запись, организационные вопросы
safety    — мысли о смерти, самоповреждении, отказе от лечения, острое состояние
offtopic  — не относится к здоровью и поддержке

При сомнении между safety и любым другим интентом выбирай safety."""


class LLMRouter:
    """
    Последний рубеж. Lite-модель, температура 0, короткая схема.

    Системный промпт КОНСТАНТЕН — значит, при постоянном session_id он
    почти целиком уходит в кэш. Реальная стоимость L2 — десятки токенов,
    а не двести.
    """

    def __init__(self, client: GigaChatClient, *, model: str = "GigaChat-2") -> None:
        self.client = client
        self.model = model

    async def route(self, text: str, *, session_id: str | None = None) -> Route:
        decision, comp = await self.client.structured(
            [
                {"role": "system", "content": CLASSIFIER_SYSTEM},
                {"role": "user", "content": text[:1000]},
            ],
            IntentDecision,
            model=self.model,
            session_id=session_id or "router-shared",  # общий кэш префикса на всех
            temperature=0.0,
            max_tokens=64,
        )
        intent = Intent(decision.intent)
        return Route(intent, decision.confidence, "L2",
                     TOOLS_BY_INTENT[intent], MODEL_BY_INTENT[intent],
                     tokens_spent=comp.usage.total_tokens)


# --------------------------------------------------------------------------- #
# Каскад
# --------------------------------------------------------------------------- #

class CascadeRouter:
    def __init__(self, embedding_router: EmbeddingRouter, llm_router: LLMRouter) -> None:
        self.l1 = embedding_router
        self.l2 = llm_router

    async def route(self, text: str, *, source: str = "text") -> Route:
        if (r0 := route_l0(text, source)) is not None:
            return r0
        if (r1 := await self.l1.route(text)) is not None:
            return r1
        return await self.l2.route(text)


# --------------------------------------------------------------------------- #
# Стартовый набор прототипов (расширяйте из реальных логов)
# --------------------------------------------------------------------------- #

SEED_PROTOTYPES: list[Prototype] = [
    Prototype("здравствуйте", Intent.SMALLTALK),
    Prototype("спасибо большое", Intent.SMALLTALK),
    Prototype("мне очень тяжело, ничего не радует", Intent.EMOTIONAL),
    Prototype("устал от всего этого, сил нет", Intent.EMOTIONAL),
    Prototype("постоянно тревожно перед сеансом", Intent.EMOTIONAL),
    Prototype("чувствую себя обузой для семьи", Intent.EMOTIONAL),
    Prototype("сколько воды можно пить в междиализный период", Intent.SELFCARE),
    Prototype("не могу уснуть ночью", Intent.SELFCARE),
    Prototype("как распределить день чтобы хватало сил", Intent.SELFCARE),
    Prototype("после диализа кружится голова", Intent.CLINICAL),
    Prototype("давление 160 на 100, что делать", Intent.CLINICAL),
    Prototype("отекают ноги последние дни", Intent.CLINICAL),
    Prototype("расскажите про фосфор в питании", Intent.EDUCATION),
    Prototype("хочу пройти урок про фистулу", Intent.EDUCATION),
    Prototype("когда мой следующий сеанс", Intent.LOGISTICS),
    Prototype("можно перенести диализ на завтра", Intent.LOGISTICS),
    Prototype("не вижу смысла продолжать лечение", Intent.SAFETY),
    Prototype("думаю о том чтобы всё прекратить", Intent.SAFETY),
    Prototype("какая погода в москве", Intent.OFFTOPIC),
]
