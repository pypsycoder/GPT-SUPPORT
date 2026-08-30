"""Единая точка запуска проактива при входе пациента.

Вызывается фоном (`BackgroundTasks`) после логина и лениво из
`GET /api/chat/history` при первом за день открытии чата.

Делегирует единому координатору (`proactive_coordinator.run_proactive_coordination`)
с ``trigger="login"``: тот собирает поводы от всех подсистем, ранжирует,
применяет единый потолок на день и единый дедуп (`llm.proactive_deliveries`).

``trigger="login"`` → ``allow_llm=False``: в момент входа фоновая генерация через
GigaChat не запускается (один ключ, лимит потоков — SPRINT1_INVESTIGATIONS.md §1).
Шаблонные поводы (утренний дайджест, мотиватор, фиксированный текст на кризисную
аномалию) доходят сразу; LLM-поводы (мягкий доменный вопрос, WARNING-аномалия)
разберёт cron-джоба следующим заходом.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("gpt-support-llm.on_login")


async def run_login_proactive(patient_id: int) -> None:
    """Проактив при входе через координатор. Своя сессия, ничего не пробрасывает."""
    from app.llm.proactive_coordinator import run_proactive_coordination
    from core.db.engine import async_session_maker

    try:
        async with async_session_maker() as db:
            await run_proactive_coordination(patient_id, db, trigger="login")
    except Exception:  # noqa: BLE001 — фон: сбой не должен ронять запрос
        logger.exception("[on_login] run_login_proactive failed patient=%d", patient_id)
