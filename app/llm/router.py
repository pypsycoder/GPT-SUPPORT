"""
LLM Request Router — классификатор входящих запросов.

Определяет:
  - RequestType: тип запроса (кнопка, простой, клинический, эмоциональный...)
  - ModelTier: какую модель GigaChat использовать
  - domain_hint: тематика (sleep / emotion / routine / stress / self_care / social / motivation)
  - priority: 1 (фон) | 2 (обычный) | 3 (срочный)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

def _is_emergency_vitals(text: str) -> bool:
    """Числовой порог: систолическое АД >= 180 = гипертонический криз."""
    for val in re.findall(r'\b(\d{3,})\b|(\d{3,})(?=/)', text):
        num = val[0] or val[1]
        if num and int(num) >= 180:
            return True
    return False


from app.llm.keywords import (
    CLINICAL_KEYWORDS,
    DOMAIN_KEYWORDS,
    EMOTIONAL_KEYWORDS,
    SAFETY_KEYWORDS,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RequestType(str, Enum):
    QUICK_ACTION = "quick_action"   # нажатие кнопки интерфейса
    SIMPLE       = "simple"         # короткий/нейтральный текст
    CLINICAL     = "clinical"       # клинические симптомы
    EMOTIONAL    = "emotional"      # эмоциональный запрос
    PROACTIVE    = "proactive"      # системный проактивный запрос
    SAFETY       = "safety"         # кризис / угроза жизни


class ModelTier(str, Enum):
    LITE = "lite"   # GigaChat-2-Lite — быстрые короткие ответы
    PRO  = "pro"    # GigaChat-2-Pro  — основная модель
    MAX  = "max"    # GigaChat-2-Max  — кризис и сложные случаи


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class RouterResult:
    request_type: RequestType
    model_tier: ModelTier
    domain_hint: str | None  # "sleep" | "emotion" | "routine" | "stress" | "self_care" | "social" | "motivation"
    priority: int            # 1 = фон, 2 = обычный, 3 = срочный


# ---------------------------------------------------------------------------
# Domain detection
# ---------------------------------------------------------------------------

def detect_domain(text: str) -> str | None:
    """
    Определяет тематический домен по тексту.
    Возвращает первый совпавший домен или None.
    Порядок доменов влияет на приоритет при нескольких совпадениях.
    """
    lower = text.lower()
    domain_priority = [
        "sleep",
        "stress",
        "emotion",
        "social",
        "motivation",
        "routine",
        "self_care",
    ]
    scores: dict[str, int] = {}
    for domain in domain_priority:
        keywords = DOMAIN_KEYWORDS.get(domain, [])
        count = sum(1 for kw in keywords if kw in lower)
        if count > 0:
            scores[domain] = count

    if not scores:
        return None
    # Домен с наибольшим числом совпадений
    return max(scores, key=lambda d: scores[d])


# ---------------------------------------------------------------------------
# Request classifier
# ---------------------------------------------------------------------------

def classify_request(text: str, source: str) -> RouterResult:
    """
    Классифицирует запрос по тексту и источнику.

    Args:
        text:   текст запроса (может быть пустым для кнопок)
        source: "button" | "text" | "system"

    Returns:
        RouterResult с типом, моделью, доменом и приоритетом
    """
    lower = text.lower()
    domain = detect_domain(text)

    # 1. Нажатие кнопки — быстрый ответ, Lite
    if source == "button":
        return RouterResult(
            request_type=RequestType.QUICK_ACTION,
            model_tier=ModelTier.LITE,
            domain_hint=domain,
            priority=1,
        )

    # 2. Кризисные слова — максимальная модель, высший приоритет
    if any(kw in lower for kw in SAFETY_KEYWORDS):
        return RouterResult(
            request_type=RequestType.SAFETY,
            model_tier=ModelTier.MAX,
            domain_hint=domain,
            priority=3,
        )

    # 2b. Экстремальные витальные показатели — тоже SAFETY
    if _is_emergency_vitals(text):
        return RouterResult(
            request_type=RequestType.SAFETY,
            model_tier=ModelTier.MAX,
            domain_hint="self_care",
            priority=3,
        )

    # 3. Клинические симптомы — Pro, повышенный приоритет
    if any(kw in lower for kw in CLINICAL_KEYWORDS):
        return RouterResult(
            request_type=RequestType.CLINICAL,
            model_tier=ModelTier.PRO,
            domain_hint=domain,
            priority=2,
        )

    # 4. Эмоциональный запрос — Pro, повышенный приоритет
    if any(kw in lower for kw in EMOTIONAL_KEYWORDS):
        return RouterResult(
            request_type=RequestType.EMOTIONAL,
            model_tier=ModelTier.PRO,
            domain_hint=domain,
            priority=2,
        )

    # 5. Системный проактивный запрос
    if source == "system":
        return RouterResult(
            request_type=RequestType.PROACTIVE,
            model_tier=ModelTier.PRO,
            domain_hint=domain,
            priority=1,
        )

    # 6. Короткий нейтральный запрос — Lite
    if len(text.strip()) < 30:
        return RouterResult(
            request_type=RequestType.SIMPLE,
            model_tier=ModelTier.LITE,
            domain_hint=domain,
            priority=1,
        )

    # 7. Всё остальное — Pro
    return RouterResult(
        request_type=RequestType.SIMPLE,
        model_tier=ModelTier.PRO,
        domain_hint=domain,
        priority=1,
    )
