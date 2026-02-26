"""
APScheduler — планировщик проактивных сообщений.

Три задания (timezone="Europe/Moscow"):
  proactive_morning   — 08:00
  proactive_afternoon — 14:00
  proactive_evening   — 20:00

Каждое задание:
  1. Получает список активных пациентов (is_onboarded=True, is_locked=False).
  2. Для каждого вызывает deliver_proactive_messages в отдельной DB-сессии.

API:
  start_scheduler() — регистрирует задания и запускает планировщик.
  stop_scheduler()  — останавливает планировщик (wait=False).
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("gpt-support-llm.scheduler")

_scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


async def _run_proactive_job() -> None:
    """
    Получает всех активных пациентов и запускает deliver_proactive_messages
    для каждого в отдельной сессии БД.
    """
    from sqlalchemy import select

    from app.llm.proactive import deliver_proactive_messages
    from app.users.models import User
    from core.db.engine import async_session_maker

    # Загружаем список пациентов в одной сессии
    patient_ids: list[int] = []
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(User.id).where(
                    User.is_onboarded == True,  # noqa: E712
                    User.is_locked == False,    # noqa: E712
                )
            )
            patient_ids = list(result.scalars().all())
    except Exception as exc:
        logger.error("[scheduler] Не удалось получить список пациентов: %s", exc)
        return

    logger.info("[scheduler] Проактивные сообщения: %d пациентов", len(patient_ids))

    # Каждый пациент — отдельная сессия, чтобы изолировать ошибки
    for patient_id in patient_ids:
        async with async_session_maker() as db:
            try:
                await deliver_proactive_messages(patient_id, db)
            except Exception as exc:
                logger.error(
                    "[scheduler] patient=%d ошибка: %s", patient_id, exc
                )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start_scheduler() -> None:
    """Регистрирует задания и запускает AsyncIOScheduler."""
    _scheduler.add_job(
        _run_proactive_job,
        trigger="cron",
        hour=8,
        minute=0,
        id="proactive_morning",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_proactive_job,
        trigger="cron",
        hour=14,
        minute=0,
        id="proactive_afternoon",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_proactive_job,
        trigger="cron",
        hour=20,
        minute=0,
        id="proactive_evening",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("[scheduler] APScheduler запущен. Задания: 08:00, 14:00, 20:00 MSK")


def stop_scheduler() -> None:
    """Останавливает планировщик без ожидания завершения текущих задач."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] APScheduler остановлен")
