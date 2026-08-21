"""
L2 — последний уровень каскада: Lite + structured output (00_MANUAL.md, часть 8).

Системный промпт константный → при общем ``session_id="router-shared"`` он
уходит в кэш один раз для всех пациентов (никаких данных пациента в
константе нет — только литерал строки, ПДн не касается, часть 13 манула).

Схема — одно обязательное поле, по той же причине, что и ``AgentReply``
(``app/llm/agent/schemas.py`` уже задокументировал на своём замере: лишнее
поле роняет карточку на грани). Роутеру не нужен домен или уверенность от
модели — домен уже даёт ``detect_domain()``, а решение "доверять ли ответу"
здесь не стоит: L2 — последний уровень, отвечать обязан.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.llm.errors import LLMError

logger = logging.getLogger("gpt-support-llm.router_l2")

ENV_FLAG = "LLM_ROUTER_L2"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

SHARED_SESSION_ID = "router-shared"

_SYSTEM_PROMPT = (
    "Ты классифицируешь одно сообщение пациента на программном гемодиализе "
    "для маршрутизации внутри медицинского приложения поддержки. Определи "
    "request_type:\n"
    "  simple — нейтральный текст, малый разговор, вопрос не по теме здоровья;\n"
    "  clinical — показатели, симптомы, лекарства, самочувствие тела;\n"
    "  emotional — тревога, грусть, страх, эмоциональная поддержка;\n"
    "  safety — угроза жизни, суицидальные мысли, острое опасное состояние.\n"
    "При сомнении между safety и любым другим вариантом — всегда выбирай "
    "safety: пропустить кризис дороже, чем один лишний осторожный ответ.\n\n"
    # Без этой строки Lite на однопольной схеме часто отвечает голым словом
    # ("clinical") или "поле: значение" вместо JSON, и валидация падает на
    # первой попытке (замерено вживую: 4/5 → 0 повторов с этой инструкцией,
    # без неё падало почти постоянно). Формулировка — та же, что уже
    # проверена в app/llm/agent/prompts.py::AGENT_SYSTEM_PROMPT.
    'Верни ОДИН JSON-объект строго по схеме {"request_type": "..."}, '
    "без markdown и без пояснений."
)


def l2_enabled() -> bool:
    return str(os.getenv(ENV_FLAG, "")).strip().lower() in _TRUTHY


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
