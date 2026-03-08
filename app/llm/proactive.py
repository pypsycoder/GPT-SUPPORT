"""
Proactive Message Generator — генератор проактивных сообщений.

generate_daily_queue(patient_id, db) -> list[ProactiveMessage]
  Формирует очередь до 3 сообщений на день.
  Приоритет: CRITICAL аномалии → WARNING аномалии → домены с худшим score.

deliver_proactive_messages(patient_id, db)
  Генерирует и сохраняет проактивные сообщения в chat_messages.
  Проверяет дубли: не отправляет, если proactive-сообщение уже было за 6 часов.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.anomaly import AnomalyAlert, check_anomalies
from app.llm.router import ModelTier, RequestType, RouterResult

logger = logging.getLogger("gpt-support-llm.proactive")

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
# Формирование очереди
# ---------------------------------------------------------------------------


async def generate_daily_queue(
    patient_id: int,
    db: AsyncSession,
) -> list[ProactiveMessage]:
    """
    Формирует список проактивных сообщений (не более 3).

    Приоритет:
      1. CRITICAL аномалии (request_type=SAFETY, model=PRO)
      2. WARNING аномалии  (request_type=PROACTIVE, model=LITE)
      3. Домены с худшим score < 0.5 (request_type=PROACTIVE, model=LITE)
    """
    from app.llm.domain_scorer import calculate_domain_scores, get_priority_domains

    messages: list[ProactiveMessage] = []

    # --- Аномалии ---
    anomalies = await check_anomalies(patient_id, db)
    critical = [a for a in anomalies if a.severity == "CRITICAL"]
    warnings = [a for a in anomalies if a.severity == "WARNING"]

    for alert in critical:
        if len(messages) >= 3:
            break
        messages.append(_make_anomaly_message(patient_id, alert))

    for alert in warnings:
        if len(messages) >= 3:
            break
        messages.append(_make_anomaly_message(patient_id, alert))

    # --- Домены с плохим score ---
    if len(messages) < 3:
        try:
            scores = await calculate_domain_scores(patient_id, db)
            logger.info(
                "[proactive] domain scores patient=%d: %s", patient_id, scores
            )
            priority_domains = get_priority_domains(scores)
            for domain in priority_domains:
                if len(messages) >= 3:
                    break
                # Не дублируем домен, уже охваченный аномалией
                if any(m.domain_hint == domain for m in messages):
                    continue
                score = scores[domain]
                if score is not None and score < 0.5:
                    messages.append(_make_domain_message(patient_id, domain, score))
        except Exception as exc:
            logger.warning(
                "[proactive] domain scoring failed patient=%d: %s", patient_id, exc
            )

    return messages


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


# ---------------------------------------------------------------------------
# Доставка сообщений
# ---------------------------------------------------------------------------


async def deliver_proactive_messages(patient_id: int, db: AsyncSession) -> None:
    """
    Генерирует и сохраняет проактивные сообщения для пациента.

    Пропускает доставку, если proactive-сообщение уже было за последние 6 часов
    (защита от дублей при рестарте сервера).

    Сохраняет assistant-сообщения в llm.chat_messages с request_type="proactive".
    """
    from app.llm.agent import generate_response
    from app.models.llm import ChatMessage

    # --- Проверка дублей (6 часов) ---
    since_6h = datetime.utcnow() - timedelta(hours=6)
    dup_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.patient_id == patient_id,
            ChatMessage.role == "assistant",
            ChatMessage.request_type == "proactive",
            ChatMessage.created_at >= since_6h,
        )
        .limit(1)
    )
    if dup_result.scalar_one_or_none() is not None:
        logger.info(
            "[proactive] пропуск patient=%d — proactive уже было за последние 6ч",
            patient_id,
        )
        return

    # --- Формируем очередь ---
    queue = await generate_daily_queue(patient_id, db)
    if not queue:
        logger.info("[proactive] patient=%d — нет сообщений для отправки", patient_id)
        return

    # --- Генерируем ответы и сохраняем ---
    for msg in queue:
        try:
            result_dict = await generate_response(
                patient_id=patient_id,
                user_input=msg.user_input,
                router_result=msg.router_result,
                context={},
                db=db,
            )
            assistant_msg = ChatMessage(
                patient_id=patient_id,
                role="assistant",
                content=result_dict["response"],
                tokens_used=result_dict["tokens_input"] + result_dict["tokens_output"],
                model_used=result_dict["model"],
                domain=result_dict["domain"],
                request_type="proactive",
            )
            db.add(assistant_msg)
            await db.flush()
            logger.info(
                "[proactive] patient=%d domain=%s trigger=%s",
                patient_id,
                msg.domain_hint,
                msg.trigger_reason,
            )
        except Exception as exc:
            logger.error(
                "[proactive] Ошибка генерации patient=%d domain=%s: %s",
                patient_id,
                msg.domain_hint,
                exc,
            )

    await db.commit()
