from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.exc import SQLAlchemyError

from app.llm.errors import LLMError


_CONCURRENCY = 5

logger = logging.getLogger("gpt-support-llm.scheduler")
_scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


async def _get_active_patient_ids() -> list[int]:
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
    except SQLAlchemyError as exc:
        logger.error("[scheduler] failed to fetch active patients: %s", exc)
    return patient_ids


async def _run_proactive_job() -> None:
    from app.llm.proactive import deliver_proactive_messages
    from core.db.engine import async_session_maker

    patient_ids = await _get_active_patient_ids()
    logger.info("[scheduler] proactive job: %d patients", len(patient_ids))

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _process(patient_id: int) -> None:
        async with sem:
            async with async_session_maker() as db:
                try:
                    await deliver_proactive_messages(patient_id, db)
                except (LLMError, SQLAlchemyError, ValueError, TypeError, KeyError) as exc:
                    logger.error("[scheduler] patient=%d failed: %s", patient_id, exc)

    await asyncio.gather(*(_process(pid) for pid in patient_ids))


async def _run_morning_job() -> None:
    from app.llm.morning_service import deliver_morning_message
    from core.db.engine import async_session_maker

    patient_ids = await _get_active_patient_ids()
    logger.info("[scheduler] morning job: %d patients", len(patient_ids))

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _process(patient_id: int) -> None:
        async with sem:
            async with async_session_maker() as db:
                try:
                    await deliver_morning_message(patient_id, db)
                except (SQLAlchemyError, ValueError, TypeError, KeyError) as exc:
                    logger.error("[scheduler] morning patient=%d failed: %s", patient_id, exc)

    await asyncio.gather(*(_process(pid) for pid in patient_ids))


def start_scheduler() -> None:
    if _scheduler.running:
        logger.info("[scheduler] already running")
        return

    _scheduler.remove_all_jobs()
    _scheduler.add_job(
        _run_morning_job,
        trigger="cron",
        hour=8,
        minute=0,
        id="morning_context",
        replace_existing=True,
    )
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
    logger.info("[scheduler] started")


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] stopped")
