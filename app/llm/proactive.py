"""
Proactive Message Generator — построение отдельных проактивных сообщений.

Сбор кандидатов, ранжирование, потолок и доставка — за
``app/llm/proactive_coordinator.py``. Этот модуль даёт ему сырьё:

_make_anomaly_message(patient_id, alert) -> ProactiveMessage
  Текст+router_result под одну аномалию (CRITICAL → SAFETY/PRO, иначе PROACTIVE/LITE).

_make_domain_message(patient_id, domain, score) -> ProactiveMessage
  Текст+router_result под домен с плохим score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.llm.anomaly import AnomalyAlert
from app.llm.pipeline import LLMPipeline
from app.llm.router import ModelTier, RequestType, RouterResult

logger = logging.getLogger("gpt-support-llm.proactive")
_llm_pipeline = LLMPipeline()

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Человекочитаемые названия доменов (для подстановки в промпт)
_DOMAIN_LABELS: dict[str, str] = {
    "sleep": "сон",
    "medication": "приём лекарств",
    "vitals": "самочувствие",
    "emotion": "эмоциональное состояние",
    "routine": "распорядок дня",
    "stress": "стресс и напряжение",
    "self_care": "уход за собой",
    "social": "общение с близкими",
    "motivation": "мотивацию и силы",
}


# ---------------------------------------------------------------------------
# Модели данных
# ---------------------------------------------------------------------------


@dataclass
class ProactiveMessage:
    patient_id: int
    domain_hint: str | None
    router_result: RouterResult
    trigger_reason: str  # для лога: почему отправляем
    user_input: str      # текст запроса, передаётся в generate_response


# ---------------------------------------------------------------------------
# Построение отдельных сообщений — используется координатором
# (app/llm/proactive_coordinator.py: _anomaly_candidates/_domain_score_candidates)
# ---------------------------------------------------------------------------


def _make_anomaly_message(patient_id: int, alert: AnomalyAlert) -> ProactiveMessage:
    is_critical = alert.severity == "CRITICAL"
    request_type = RequestType.SAFETY if is_critical else RequestType.PROACTIVE
    model_tier = ModelTier.PRO if is_critical else ModelTier.LITE

    _type_labels = {
        "systolic_bp": f"давление {int(alert.value)} мм рт.ст.",
        "pulse": f"пульс {int(alert.value)} уд/мин",
        "weight_gain": f"прибавка веса +{alert.value:.1f} кг",
    }
    label = _type_labels.get(alert.type, f"{alert.type}={alert.value}")
    trigger = f"{alert.severity} anomaly: {alert.type}={alert.value}"

    prompt_template = _load_prompt("proactive_anomaly.txt") or (
        "Мягко обратись к пациенту: сегодня зафиксировано {label}. "
        "Вырази заботу и спроси, как он себя чувствует прямо сейчас. "
        "Не давай медицинских советов — только поддержка и внимание."
    )
    user_input = prompt_template.format(label=label)

    return ProactiveMessage(
        patient_id=patient_id,
        domain_hint=alert.domain_hint,
        router_result=RouterResult(
            request_type=request_type,
            model_tier=model_tier,
            domain_hint=alert.domain_hint,
            priority=3 if is_critical else 2,
        ),
        trigger_reason=trigger,
        user_input=user_input,
    )


def _make_domain_message(
    patient_id: int, domain: str, score: float
) -> ProactiveMessage:
    trigger = f"worst domain: {domain} score={score:.2f}"
    domain_label = _DOMAIN_LABELS.get(domain, domain)

    prompt_template = _load_prompt("proactive_morning.txt") or (
        "Мягко поприветствуй пациента. Спроси один простой тёплый вопрос "
        "о его {domain_label}. Не давай советов — только живой интерес."
    )
    user_input = prompt_template.format(domain_label=domain_label, domain=domain)

    return ProactiveMessage(
        patient_id=patient_id,
        domain_hint=domain,
        router_result=RouterResult(
            request_type=RequestType.PROACTIVE,
            model_tier=ModelTier.LITE,
            domain_hint=domain,
            priority=1,
        ),
        trigger_reason=trigger,
        user_input=user_input,
    )


# ---------------------------------------------------------------------------
# Загрузка промптов
# ---------------------------------------------------------------------------


def _load_prompt(filename: str) -> str | None:
    """Читает файл промпта. Возвращает None если файл не найден."""
    path = _PROMPTS_DIR / filename
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
