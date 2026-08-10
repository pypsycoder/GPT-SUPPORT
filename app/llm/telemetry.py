"""
Телеметрия сырых вызовов GigaChat API.

Пишет каждый вызов ``GigaChatClient.call()`` в ``llm.llm_call_log`` — источник
для расчёта cache_hit (доля ``precached_tokens``) и оплачиваемых токенов.
Вызывается фоново из ``app.llm.pool``: запись не должна замедлять и не должна
ронять основной поток при ошибке БД.
"""

from __future__ import annotations

import logging

from core.db.session import async_session_factory

logger = logging.getLogger("gpt-support-llm.telemetry")


async def log_call(
    *,
    account_id: str,
    model: str,
    step: str | None = None,
    patient_id: int | None = None,
    session_key: str | None = None,
    prefix_fp: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    precached_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: int = 0,
    finish_reason: str | None = None,
    ok: bool = True,
    error: str | None = None,
) -> None:
    try:
        from app.models.llm import LLMCallLog

        async with async_session_factory() as session:
            session.add(
                LLMCallLog(
                    account_id=account_id,
                    model=model,
                    step=step,
                    patient_id=patient_id,
                    session_key=session_key,
                    prefix_fp=prefix_fp,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    precached_tokens=precached_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                    finish_reason=finish_reason,
                    ok=ok,
                    error=error,
                )
            )
            await session.commit()
    except Exception:
        logger.warning("[telemetry] failed to write llm_call_log", exc_info=True)
