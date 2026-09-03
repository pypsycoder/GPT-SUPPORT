from __future__ import annotations

import asyncio
import logging
import random

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.llm.errors import LLMError
from app.llm.pool import pool


# Проактивная рассылка идёт через координатор, который на части поводов зовёт
# LLM. Конкурентность задаёт активный провайдер (`pool.proactive_concurrency`):
# Сбер — число ключей (1 поток/ключ, SPRINT1_INVESTIGATIONS.md §1); Cloud.ru —
# CLOUD_RU_CONCURRENCY. Джиттер оставляем — пайплайн одного пациента это
# несколько последовательных вызовов, пачкой на лимит RPM легко налететь.
_PROACTIVE_CONCURRENCY = max(1, pool.proactive_concurrency)
_PROACTIVE_JITTER_SEC = (0.5, 1.5)

logger = logging.getLogger("gpt-support-llm.scheduler")
_scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# Один держатель advisory-lock на процесс. Соединение держится открытым всё время
# жизни планировщика — advisory-lock в PostgreSQL живёт в рамках сессии.
_scheduler_lock_conn: AsyncConnection | None = None


async def acquire_scheduler_lock() -> bool:
    """Взять глобальный advisory-lock планировщика.

    Гарантия «один планировщик на кластер»: при ``uvicorn --workers N`` или
    нескольких инстансах lock получит только один процесс, остальные пропустят
    старт. Идемпотентна: повторный вызов из того же процесса вернёт ``True``.
    """
    global _scheduler_lock_conn

    from sqlalchemy import text

    from app.core.config import settings
    from core.db.engine import engine

    if _scheduler_lock_conn is not None:
        return True

    conn = await engine.connect()
    result = await conn.execute(
        text("SELECT pg_try_advisory_lock(:lock_id)"),
        {"lock_id": settings.scheduler_lock_id},
    )
    has_lock = bool(result.scalar())
    if not has_lock:
        await conn.close()
        return False

    _scheduler_lock_conn = conn
    return True


async def release_scheduler_lock() -> None:
    """Отпустить advisory-lock и закрыть удерживающее соединение."""
    global _scheduler_lock_conn

    from sqlalchemy import text

    from app.core.config import settings

    if _scheduler_lock_conn is None:
        return

    try:
        await _scheduler_lock_conn.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": settings.scheduler_lock_id},
        )
    finally:
        await _scheduler_lock_conn.close()
        _scheduler_lock_conn = None


async def _get_active_patient_ids() -> list[int]:
    from sqlalchemy import select

    from app.users.models import User
    from core.db.engine import async_session_maker

    patient_ids: list[int] = []
    try:
        async with async_session_maker() as db:
            # Доставка проактива — только веб (сообщение ждёт в истории чата),
            # поэтому по telegram_id НЕ фильтруем: раньше это молча выкидывало
            # из рассылки всех, у кого нет Telegram.
            result = await db.execute(
                select(User.id).where(
                    User.is_onboarded == True,           # noqa: E712
                    User.is_locked == False,             # noqa: E712
                    User.consent_personal_data == True,  # noqa: E712
                )
            )
            patient_ids = list(result.scalars().all())
    except SQLAlchemyError as exc:
        logger.error("[scheduler] failed to fetch active patients: %s", exc)
    return patient_ids


async def _run_coordinator_job(trigger: str) -> None:
    """Один проход проактивного координатора по всем активным пациентам.

    Заменил три отдельных джобы (morning / proactive / motivator): координатор
    сам собирает поводы от всех подсистем, ранжирует, применяет единый потолок
    на день и единый дедуп (``llm.proactive_deliveries``).
    """
    from app.llm.proactive_coordinator import run_proactive_coordination
    from core.db.engine import async_session_maker

    patient_ids = await _get_active_patient_ids()
    logger.info("[scheduler] coordinator job trigger=%s: %d patients", trigger, len(patient_ids))

    sem = asyncio.Semaphore(_PROACTIVE_CONCURRENCY)

    async def _process(patient_id: int) -> None:
        async with sem:
            await asyncio.sleep(random.uniform(*_PROACTIVE_JITTER_SEC))
            async with async_session_maker() as db:
                try:
                    await run_proactive_coordination(patient_id, db, trigger=trigger)
                except (LLMError, SQLAlchemyError, ValueError, TypeError, KeyError) as exc:
                    logger.error(
                        "[scheduler] coordinator patient=%d trigger=%s failed: %s",
                        patient_id, trigger, exc,
                    )

    await asyncio.gather(*(_process(pid) for pid in patient_ids))


def start_scheduler() -> None:
    if _scheduler.running:
        logger.info("[scheduler] already running")
        return

    _scheduler.remove_all_jobs()
    for hour, trigger_name, job_id in (
        (8, "cron_morning", "proactive_morning"),
        (14, "cron_afternoon", "proactive_afternoon"),
        (20, "cron_evening", "proactive_evening"),
    ):
        _scheduler.add_job(
            _run_coordinator_job,
            trigger="cron",
            hour=hour,
            minute=0,
            args=[trigger_name],
            id=job_id,
            replace_existing=True,
        )
    _scheduler.start()
    logger.info("[scheduler] started (proactive coordinator, 3 daily passes)")


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] stopped")
