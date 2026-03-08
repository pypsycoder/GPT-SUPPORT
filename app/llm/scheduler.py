"""
APScheduler — планировщик проактивных сообщений.

Три задания (timezone="Europe/Moscow"):
  proactive_morning   — 08:00
  proactive_afternoon — 14:00
  proactive_evening   — 20:00

Каждое задание:
  1. Получает список активных пациентов (is_onboarded=True, is_locked=False,
     consent_personal_data=True, telegram_id IS NOT NULL).
  2. Для каждого вызывает deliver_proactive_messages в отдельной DB-сессии.

API:
  start_scheduler() — регистрирует задания и запускает планировщик.
  stop_scheduler()  — останавливает планировщик (wait=False).
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Ограничение параллельных задач: не превышать ёмкость пула GigaChat
_CONCURRENCY = 5

logger = logging.getLogger("gpt-support-llm.scheduler")

_scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


async def _get_active_patient_ids() -> list[int]:
    """Возвращает список ID пациентов, которым можно отправлять проактивные сообщения.

    Условия:
      - is_onboarded=True      — прошли онбординг
      - is_locked=False        — аккаунт не заблокирован
      - consent_personal_data  — дали согласие на обработку данных
      - telegram_id IS NOT NULL — подключён Telegram (есть куда доставить)
    """
    from sqlalchemy import select
    from app.users.models import User
    from core.db.engine import async_session_maker

    patient_ids: list[int] = []
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(User.id).where(
                    User.is_onboarded == True,           # noqa: E712
                    User.is_locked == False,             # noqa: E712
                    User.consent_personal_data == True,  # noqa: E712
                    User.telegram_id.isnot(None),
                )
            )
            patient_ids = list(result.scalars().all())
    except Exception as exc:
        logger.error("[scheduler] Не удалось получить список пациентов: %s", exc)
    return patient_ids


async def _run_proactive_job() -> None:
    """
    Получает всех активных пациентов и запускает deliver_proactive_messages
    параллельно, ограничивая конкурентность семафором.
    """
    from app.llm.proactive import deliver_proactive_messages
    from core.db.engine import async_session_maker

    patient_ids = await _get_active_patient_ids()
    logger.info("[scheduler] Проактивные сообщения: %d пациентов", len(patient_ids))

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _process(patient_id: int) -> None:
        async with sem:
            async with async_session_maker() as db:
                try:
                    await deliver_proactive_messages(patient_id, db)
                except Exception as exc:
                    logger.error("[scheduler] patient=%d ошибка: %s", patient_id, exc)

    await asyncio.gather(*(_process(pid) for pid in patient_ids))


async def _run_morning_job() -> None:
    """
    08:00 MSK — шаблонное утреннее сообщение для каждого активного пациента.
    Использует build_daily_context + build_morning_message (без LLM).
    Выполняется параллельно, ограничение — семафор _CONCURRENCY.
    """
    from app.llm.morning_service import deliver_morning_message
    from core.db.engine import async_session_maker

    patient_ids = await _get_active_patient_ids()
    logger.info("[scheduler] Утренние сообщения: %d пациентов", len(patient_ids))

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _process(patient_id: int) -> None:
        async with sem:
            async with async_session_maker() as db:
                try:
                    await deliver_morning_message(patient_id, db)
                except Exception as exc:
                    logger.error("[scheduler] morning patient=%d ошибка: %s", patient_id, exc)

    await asyncio.gather(*(_process(pid) for pid in patient_ids))


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def start_scheduler() -> None:
    """Регистрирует задания и запускает AsyncIOScheduler."""
    # Утреннее шаблонное сообщение (без LLM) — только в 08:00
    _scheduler.add_job(
        _run_morning_job,
        trigger="cron",
        hour=8,
        minute=0,
        id="morning_context",
        replace_existing=True,
    )
    # GigaChat-проактивные (аномалии, домены) — 08:00, 14:00, 20:00
    _scheduler.add_job(
        _run_proactive_job,
        trigger="cron",
        hour=8,
        minute=5,
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
    logger.info("[scheduler] APScheduler запущен. Morning: 08:00, Proactive: 08:05/14:00/20:00 MSK")


def stop_scheduler() -> None:
    """Останавливает планировщик без ожидания завершения текущих задач."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] APScheduler остановлен")
