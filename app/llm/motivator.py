"""
Motivator — проактивные сообщения при простое активности по доменам.

Запускается планировщиком в 19:00 МСК. Для каждого активного пациента
проверяет, сколько дней прошло с последней активности по ключевым доменам.
При превышении порога отправляет одно мягкое мотивационное сообщение
(без обвинений, с конкретным микродействием).

Приоритет доменов при одновременном простое:
  medications > vitals > sleep > practices > education

Одно сообщение в день на пациента — де-дупликация по ChatMessage.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import ChatMessage

logger = logging.getLogger("gpt-support-llm.motivator")

# Пороги простоя в днях
INACTIVITY_THRESHOLDS: dict[str, int] = {
    "medications": 2,
    "vitals": 3,
    "sleep": 3,
    "practices": 5,
    "education": 7,
}

_PRIORITY: dict[str, int] = {
    "medications": 1,
    "vitals": 2,
    "sleep": 3,
    "practices": 4,
    "education": 5,
}

_MESSAGES: dict[str, str] = {
    "medications": (
        "Давно не было отметок о лекарствах — уже {days} {days_word}. "
        "Если принимали, можно внести сейчас, даже задним числом."
    ),
    "vitals": (
        "{days} {days_word} без записей давления. "
        "Небольшое измерение сегодня поможет видеть динамику."
    ),
    "sleep": (
        "{days} {days_word} без записей о сне. "
        "Даже краткая отметка помогает отслеживать восстановление."
    ),
    "practices": (
        "{days} {days_word} без практик. "
        "Можно начать с самой короткой — это займёт 2–3 минуты."
    ),
    "education": (
        "{days} {days_word} без новых материалов. "
        "Есть уроки на 5 минут — может, найдётся момент сегодня?"
    ),
}

_DOMAIN_ACTIONS: dict[str, str] = {
    "medications": "open_medications",
    "vitals": "open_vitals",
    "sleep": "open_sleep",
    "practices": "open_practice",
    "education": "open_education",
}

_DOMAIN_BUTTON_LABELS: dict[str, str] = {
    "medications": "Отметить лекарства",
    "vitals": "Внести показатели",
    "sleep": "Отметить сон",
    "practices": "Открыть практики",
    "education": "Продолжить обучение",
}


def _days_word(n: int) -> str:
    if 11 <= n % 100 <= 19:
        return "дней"
    rem = n % 10
    if rem == 1:
        return "день"
    if 2 <= rem <= 4:
        return "дня"
    return "дней"


def detect_inactivity(
    last_activity: dict[str, date | None],
    today: date,
) -> list[dict]:
    """
    Возвращает домены с превышенным порогом простоя, отсортированные по приоритету.
    Домены без истории активности (None) не включаются.
    """
    inactive = []
    for domain, threshold in INACTIVITY_THRESHOLDS.items():
        last = last_activity.get(domain)
        if last is None:
            continue
        days_since = (today - last).days
        if days_since >= threshold:
            inactive.append({
                "domain": domain,
                "days": days_since,
                "priority": _PRIORITY.get(domain, 99),
            })
    inactive.sort(key=lambda x: x["priority"])
    return inactive


def _build_motivator_message(domain: str, days: int) -> dict:
    template = _MESSAGES.get(domain, "Давно не было активности в приложении.")
    text_content = template.format(days=days, days_word=_days_word(days))

    buttons = []
    action = _DOMAIN_ACTIONS.get(domain)
    label = _DOMAIN_BUTTON_LABELS.get(domain)
    if action and label:
        buttons.append({"label": label, "action": action})

    return {"text": text_content, "buttons": buttons}


async def _was_motivator_sent_today(patient_id: int, db: AsyncSession) -> bool:
    # «Сегодня» = с полуночи по часам БД (func.date(func.now())):
    # chat_messages.created_at пишется server_default NOW(), сравнивать надо в
    # том же поясе, а не по наивному времени Python-процесса.
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.patient_id == patient_id,
            ChatMessage.role == "assistant",
            ChatMessage.request_type == "motivator",
            ChatMessage.created_at >= func.date(func.now()),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


