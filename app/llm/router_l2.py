"""
L2 — последний уровень каскада: Lite + structured output (см. pipeline/STRUCTURE.md, «Роутер»).

Системный промпт константный → при общем ``session_id="router-shared"`` он
уходит в кэш один раз для всех пациентов (никаких данных пациента в
константе нет — только литерал строки, ПДн не касается, см. pipeline/STRUCTURE.md, «Ограничения и риски»).

Схема — одно обязательное поле, по той же причине, что и ``AgentReply``
(``app/llm/agent/schemas.py`` уже задокументировал на своём замере: лишнее
поле роняет карточку на грани). Роутеру не нужен домен или уверенность от
модели — домен уже даёт ``detect_domain()``, а решение "доверять ли ответу"
здесь не стоит: L2 — последний уровень, отвечать обязан.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.llm.errors import LLMError
from app.llm.structured import JSON_ONLY_INSTRUCTION

logger = logging.getLogger("gpt-support-llm.router_l2")

SHARED_SESSION_ID = "router-shared"

_SYSTEM_PROMPT = (
    "Ты классифицируешь одно сообщение пациента на программном гемодиализе "
    "для маршрутизации внутри медицинского приложения поддержки. Определи "
    "request_type:\n"
    "  simple — нейтральный текст, малый разговор, вопрос не по теме здоровья;\n"
    "  clinical — показатели, симптомы, лекарства, самочувствие тела, вопросы "
    "про дозы или схему лечения (в том числе «можно я сам изменю дозу»), "
    "если нет признаков угрозы себе;\n"
    "  emotional — тревога, грусть, страх, эмоциональная поддержка. Сюда же "
    "относится страх о ВОЗМОЖНЫХ будущих осложнениях («а что если фистула "
    "откажет», «а вдруг мне станет плохо ночью») — человек боится "
    "гипотетического сценария, а не сообщает о риске себе прямо сейчас;\n"
    "  safety — пациент сообщает об угрозе своей жизни ПРЯМО СЕЙЧАС: "
    "суицидальные мысли или намерение, самоповреждение, острое опасное "
    "состояние тела (без сознания, не может дышать, кровотечение и т.п.).\n"
    "При сомнении, есть ли в сообщении реальный риск для жизни или "
    "самоповреждения, — выбирай safety: пропустить такой кризис дороже, чем "
    "один лишний осторожный ответ. Но тревога о гипотетическом будущем и "
    "вопросы про лечение или дозы без признаков такого риска — это не "
    "safety, даже если звучат серьёзно.\n\n"
    # Без явной инструкции про формат (structured.JSON_ONLY_INSTRUCTION) Lite
    # на однопольной схеме часто отвечает голым словом ("clinical") или
    # "поле: значение" вместо JSON, и валидация падает на первой попытке
    # (замерено вживую: 4/5 → 0 повторов с этой инструкцией, без неё падало
    # почти постоянно). Схема-пример поверх общей формулировки — своя
    # добавка для однопольной схемы, не проверялась отдельно от инструкции.
    f'{JSON_ONLY_INSTRUCTION} Схема: {{"request_type": "..."}}.'
)


class RouterL2Reply(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_type: Literal["simple", "clinical", "emotional", "safety"]


async def classify(text: str) -> str | None:
    """``None`` — L2 недоступен или сломался; каскад откатится на старый роутер."""
    message = str(text or "").strip()
    if not message:
        return None

    from app.llm.pool import pool

    try:
        client = await pool.get_available("lite")
        result = await client.structured(
            [{"role": "user", "content": message}],
            _SYSTEM_PROMPT,
            RouterL2Reply,
            step="router_l2",
            session_id=SHARED_SESSION_ID,
        )
        return result.parsed.request_type
    except LLMError as exc:
        logger.warning("[router_l2] classify failed: %s", exc)
        return None
