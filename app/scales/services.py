from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Union

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.scales.calculators.hads import calculate_hads
from app.scales.calculators.kop_25a1 import calculate_kop_25a1 as calculate_kop_25a1_calc
from app.scales.config.hads import HADS_CONFIG
from app.scales.config.kop_25a1 import KOP25A_CONFIG
from app.scales.config.psqi import PSQI_CONFIG
from app.scales.config.tobol import TOBOL_CONFIG
from app.scales.models import ScaleResult
from app.scales.registry import get_scale_calculator

logger = logging.getLogger("gpt-support")


def get_scale_config(scale_code: str) -> dict:
    """Возвращаем конфиг шкалы по её коду."""

    code = scale_code.upper()
    if code == "HADS":
        return HADS_CONFIG
    if code in {"KOP25A", "KOP_25A1"}:
        return KOP25A_CONFIG
    if code == "TOBOL":
        return TOBOL_CONFIG
    if code == "PSQI":
        return PSQI_CONFIG
    raise ValueError(f"Unknown scale code: {scale_code}")


def calculate_hads_result(scale_config: dict, answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Обертка для расчёта HADS (совместимость со старыми вызовами)."""

    return calculate_hads(answers)


def calculate_kop25a_result(scale_config: dict, answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Обертка для расчёта КОП-25А1 (совместимость со старыми вызовами)."""

    return calculate_kop_25a1_calc(answers)


def calculate_tobol_result(scale_config: dict, answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Обертка для расчёта ТОБОЛ через реестр вычислителей."""

    calculator = get_scale_calculator("TOBOL")
    return calculator(answers)


def calculate_psqi_result(scale_config: dict, answers: List[Union[Dict[str, Any], "PsqiAnswerIn"]]):
    """Обертка для расчёта PSQI."""

    calculator = get_scale_calculator("PSQI")
    return calculator(answers)


async def save_scale_result(
    session: AsyncSession,
    user_id: int,
    scale_code: str,
    scale_version: str,
    result_json: Dict[str, Any],
    answers_log: List[Dict[str, Any]],
) -> ScaleResult:
    """Сохраняем результат прохождения шкалы в БД."""

    logger.info(
        "[scales] save_scale_result: user_id=%s, scale_code=%s",
        user_id, scale_code,
    )

    scale_result = ScaleResult(
        user_id=user_id,
        scale_code=scale_code,
        scale_version=scale_version,
        measured_at=datetime.now(timezone.utc),
        result_json=result_json,
        answers_json=answers_log,
    )

    try:
        session.add(scale_result)
        logger.info("[scales] session.add() — OK")

        await session.flush()
        logger.info("[scales] session.flush() — OK, id=%s", scale_result.id)

        await session.commit()
        logger.info("[scales] session.commit() — OK")

        await session.refresh(scale_result)
        logger.info("[scales] session.refresh() — OK, id=%s", scale_result.id)

        # Проверяем, реально ли запись в БД
        verify = await session.execute(
            text("SELECT id FROM scales.scale_results WHERE id = :rid"),
            {"rid": str(scale_result.id)},
        )
        row = verify.fetchone()
        if row:
            logger.info("[scales] ✅ VERIFIED in DB: id=%s", row[0])
        else:
            logger.error("[scales] ❌ NOT FOUND in DB after commit! id=%s", scale_result.id)

    except Exception:
        logger.exception("[scales] ❌ ОШИБКА при сохранении scale_result")
        raise

    return scale_result
