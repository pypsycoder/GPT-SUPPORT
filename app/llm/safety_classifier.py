"""LLM-классификатор суицидального риска — второй эшелон поверх regex-L0.

Заменил embedding-слой `crisis_semantic` (удалён 2026-08-31, не прошёл валидацию —
`docs/agent/CRISIS_SEMANTIC_VALIDATION.md`). Рубрика — из `safety-bench`
(`prompts/safety_classifier.txt`), t=0.

Модель зависит от активного LLM-провайдера (`pool.chat_provider`):
  * **sber** — GigaChat-2 Lite (тир `lite`). Валидированный прод-конфиг,
    safety-bench v1: recall {act,plan} 0.78–0.81, FPR hard-neg 0.06.
  * **cloudru** — топовая модель (тир `max` → `CLOUD_RU_MODEL_MAX`, по умолчанию
    GigaChat 3.5 Ultra). Safety-bench 2026-09-02 (holdout, продовая рубрика):
    recall {act,plan} **0.97**, FPR **0.00**.

Место в пайплайне: `boundary_guard`, ПОСЛЕ L0-regex и prompt-injection, только если
L0 не дал `urgent`. Не бросает исключений наружу: сбой API → `available=False`,
пайплайн работает как L0-only.

Рабочая точка регулируется ФОРМУЛИРОВКОЙ рубрики (`prompts/safety_classifier.txt`),
не порогом. Тюнить только на dev-сплите golden set (`tests/fixtures/safety_golden.jsonl`),
test-сплит не трогать — см. `docs/agent/SAFETY_LLM_INTEGRATION_PLAN.md` §5.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.llm.errors import LLMError
from app.llm.structured import JSON_ONLY_INSTRUCTION

logger = logging.getLogger("gpt-support-llm.safety_classifier")

ENV_FLAG = "LLM_SAFETY_LLM"
_TRUTHY = frozenset({"1", "true", "yes", "on"})
SHARED_SESSION_ID = "safety-classifier-shared"

Level = Literal[
    "none", "distress", "ideation_passive", "ideation_active", "plan_or_imminent"
]
Subject = Literal["self", "other", "abstract"]
Confidence = Literal["low", "medium", "high"]

# `confidence` — дискретный бакет, не свободный float: grammar-декодер GigaChat 3.5
# на неограниченном числовом поле склонен «убегать» (`0.9000000…`). Основной фикс
# whitespace-залипания — все поля в required (structured.response_format_for),
# enum здесь дополнительная страховка. Наружу отдаём числом для диагностики.
_CONFIDENCE_SCORE: dict[str, float] = {"low": 0.3, "medium": 0.6, "high": 0.9}

LEVELS: tuple[str, ...] = (
    "none", "distress", "ideation_passive", "ideation_active", "plan_or_imminent"
)
# Требуют своей роли субъекта и активной суицидальности.
_HIGH = frozenset({"ideation_active", "plan_or_imminent"})

_PROMPT_FILE = Path(__file__).with_name("prompts") / "safety_classifier.txt"
_SYSTEM_PROMPT = _PROMPT_FILE.read_text(encoding="utf-8").strip() + "\n\n" + JSON_ONLY_INSTRUCTION


def enabled() -> bool:
    # default ON: флаг задаётся явно только чтобы выключить (kill-switch).
    return str(os.getenv(ENV_FLAG, "true")).strip().lower() in _TRUTHY


_SUBJECT_VALUES = frozenset({"self", "other", "abstract"})


class _RiskCard(BaseModel):
    model_config = ConfigDict(extra="ignore")

    level: Level
    subject: Subject = "self"
    confidence: Confidence = "medium"

    @field_validator("level", mode="before")
    @classmethod
    def _coerce_level(cls, v: object) -> str:
        # Lite иногда путает поля (кладёт subject в level) или отвечает не по схеме.
        # `none` тут опасен — при неуверенности падаем в `distress` (concern-тир,
        # подсказка агенту), не в тишину. Совпадает со стратегией safety-bench.
        s = str(v or "").strip().lower()
        if s in LEVELS:
            return s
        return "distress"

    @field_validator("subject", mode="before")
    @classmethod
    def _coerce_subject(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        return s if s in _SUBJECT_VALUES else "self"

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        if s in _CONFIDENCE_SCORE:
            return s
        # число из старой рубрики / другого провайдера → ближайший бакет
        try:
            f = float(s)
            return "high" if f >= 0.75 else "low" if f <= 0.4 else "medium"
        except (TypeError, ValueError):
            return "medium"


@dataclass(slots=True)
class SafetyAssessment:
    level: str = "none"
    subject: str = "self"
    confidence: float = 0.0
    latency_ms: int = 0
    available: bool = False

    @property
    def is_self(self) -> bool:
        return self.subject == "self"

    @property
    def interrupt(self) -> bool:
        """Обрыв до генерации: назван способ/время/приготовления, риск у автора."""
        return self.available and self.is_self and self.level == "plan_or_imminent"

    @property
    def active_ideation(self) -> bool:
        """Активная суицидальность без плана, риск у автора — агент отвечает + жёсткая плашка."""
        return self.available and self.is_self and self.level == "ideation_active"

    @property
    def passive_ideation(self) -> bool:
        """Пассивное желание не жить, риск у автора — агент отвечает + мягкая плашка."""
        return self.available and self.is_self and self.level == "ideation_passive"

    @property
    def distress(self) -> bool:
        return self.available and self.is_self and self.level == "distress"


async def classify(text: str, context: list[str] | None = None) -> SafetyAssessment:
    """Классифицировать одну реплику пациента. Никогда не бросает."""
    message = str(text or "").strip()
    if not message:
        return SafetyAssessment(available=False)

    user_parts: list[str] = []
    ctx = [c.strip() for c in (context or []) if c and c.strip()]
    if ctx:
        joined = "\n".join(f"  [{i + 1}] {c}" for i, c in enumerate(ctx))
        user_parts.append(f"<контекст>\n{joined}\n</контекст>")
    user_parts.append(f"<сообщение>\n{message}\n</сообщение>")
    user_content = "\n\n".join(user_parts)

    from app.llm.pool import pool

    # На Cloud.ru safety идёт на топовую модель (тир max → GigaChat 3.5 Ultra),
    # на Сбере — на дешёвый Lite. Обоснование — в докстринге модуля + safety-bench.
    tier = "max" if pool.chat_provider == "cloudru" else "lite"

    try:
        client = await pool.get_available(tier)
        result = await client.structured(
            [{"role": "user", "content": user_content}],
            _SYSTEM_PROMPT,
            _RiskCard,
            temperature=0.0,
            step="safety_classifier",
            session_id=SHARED_SESSION_ID,
            max_tokens=400,
        )
    except LLMError as exc:
        logger.warning("[safety_classifier] недоступен: %s", exc)
        return SafetyAssessment(available=False)
    except Exception as exc:  # noqa: BLE001 — safety-путь не должен ронять чат
        logger.exception("[safety_classifier] неожиданный сбой: %s", exc)
        return SafetyAssessment(available=False)

    card = result.parsed
    return SafetyAssessment(
        level=card.level,
        subject=card.subject,
        confidence=_CONFIDENCE_SCORE.get(card.confidence, 0.6),
        latency_ms=int(result.latency_ms or 0),
        available=True,
    )
