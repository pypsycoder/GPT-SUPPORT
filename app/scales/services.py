# ============================================
# Scales Service: Конфигурация и сохранение результатов шкал
# ============================================
# Реестр конфигов шкал, диспетчер калькуляторов,
# сохранение результатов в ScaleResult.

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.scales.calculators.hads import calculate_hads
from app.scales.calculators.kdqol import calculate_kdqol, get_kdqol_feedback_module
from app.scales.calculators.kop_25a1 import calculate_kop_25a1 as calculate_kop_25a1_calc
from app.scales.calculators.pss10 import calculate_pss10
from app.scales.calculators.wcq_lazarus import calculate_wcq_lazarus
from app.scales.config.hads import HADS_CONFIG
from app.scales.config.kop_25a1 import KOP25A_CONFIG
from app.scales.config.psqi import PSQI_CONFIG
from app.scales.config.pss10 import PSS10_CONFIG
from app.scales.config.wcq_lazarus import WCQ_CONFIG
from app.scales.models import (
    KdqolResponse,
    KdqolSubscaleScore,
    MeasurementPoint,
    ScaleResult,
)
from app.scales.registry import get_scale_calculator

logger = logging.getLogger("gpt-support")


def get_scale_config(scale_code: str) -> dict:
    """Возвращаем конфиг шкалы по её коду."""

    code = scale_code.upper()
    if code == "HADS":
        return HADS_CONFIG
    if code in {"KOP25A", "KOP_25A1"}:
        return KOP25A_CONFIG
    if code == "PSQI":
        return PSQI_CONFIG
    if code == "PSS10":
        return PSS10_CONFIG
    if code == "WCQ_LAZARUS":
        return WCQ_CONFIG
    raise ValueError(f"Unknown scale code: {scale_code}")


def calculate_hads_result(scale_config: dict, answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Обертка для расчёта HADS (совместимость со старыми вызовами)."""

    return calculate_hads(answers)


def calculate_kop25a_result(scale_config: dict, answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Обертка для расчёта КОП-25А1 (совместимость со старыми вызовами)."""

    return calculate_kop_25a1_calc(answers)


def calculate_psqi_result(scale_config: dict, answers: List[Union[Dict[str, Any], "PsqiAnswerIn"]]):
    """Обертка для расчёта PSQI."""

    calculator = get_scale_calculator("PSQI")
    return calculator(answers)


def calculate_pss10_result(scale_config: dict, answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Обертка для расчёта ШВС-10 (PSS-10)."""

    return calculate_pss10(answers)


def calculate_wcq_lazarus_result(scale_config: dict, answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Обертка для расчёта WCQ (Опросник Лазаруса)."""

    return calculate_wcq_lazarus(answers)


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


# ============================================================
# KDQOL-SF 1.3: service functions
# ============================================================

async def kdqol_get_pending_point(
    session: AsyncSession, patient_id: int
) -> Optional[MeasurementPoint]:
    """Вернуть первую активированную незавершённую точку измерения."""
    result = await session.execute(
        select(MeasurementPoint)
        .where(
            MeasurementPoint.patient_id == patient_id,
            MeasurementPoint.completed_at.is_(None),
        )
        .order_by(MeasurementPoint.activated_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def kdqol_activate_point(
    session: AsyncSession,
    patient_id: int,
    researcher_id: int,
    point_type: str,
) -> MeasurementPoint:
    """Активировать точку измерения (T0/T1/T2) для пациента.

    Raises 409 если такой point_type уже существует.
    """
    existing = await session.execute(
        select(MeasurementPoint).where(
            MeasurementPoint.patient_id == patient_id,
            MeasurementPoint.point_type == point_type,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Точка измерения {point_type} уже активирована для этого пациента.",
        )

    mp = MeasurementPoint(
        patient_id=patient_id,
        point_type=point_type,
        activated_by=researcher_id,
        activated_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    session.add(mp)
    await session.flush()
    await session.refresh(mp)
    return mp


async def kdqol_get_patient_points(
    session: AsyncSession, patient_id: int
) -> list[MeasurementPoint]:
    """Вернуть все точки измерения пациента."""
    result = await session.execute(
        select(MeasurementPoint)
        .where(MeasurementPoint.patient_id == patient_id)
        .order_by(MeasurementPoint.point_type)
    )
    return list(result.scalars().all())


async def kdqol_process_submit(
    session: AsyncSession,
    patient_id: int,
    measurement_point_id: int,
    responses: list,
) -> dict:
    """Полный флоу сохранения ответов KDQOL: валидация → подсчёт → сохранение.

    Returns: {"success": True, "feedback_module": str | None}
    """
    # 1. Получить и проверить точку измерения
    mp = await session.get(MeasurementPoint, measurement_point_id)
    if mp is None or mp.patient_id != patient_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Точка измерения не найдена.",
        )
    if mp.completed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Опросник для этой точки измерения уже завершён.",
        )

    # 2. Собрать ответы в dict
    responses_dict: dict[str, float] = {r.question_id: r.answer_value for r in responses}

    # 3. Подсчитать субшкалы
    scores = calculate_kdqol(responses_dict)

    # 4. Сохранить ответы
    now = datetime.now(timezone.utc)
    for resp in responses:
        session.add(KdqolResponse(
            patient_id=patient_id,
            measurement_point_id=measurement_point_id,
            question_id=resp.question_id,
            answer_value=resp.answer_value,
            answered_at=now,
        ))

    # 5. Сохранить субшкалы
    for subscale_name, score in scores.items():
        session.add(KdqolSubscaleScore(
            patient_id=patient_id,
            measurement_point_id=measurement_point_id,
            subscale_name=subscale_name,
            score=score,
            calculated_at=now,
        ))

    # 6. Завершить точку
    mp.completed_at = now
    await session.flush()
    await session.commit()

    return {"success": True, "feedback_module": get_kdqol_feedback_module(scores)}


async def kdqol_get_patient_scores(
    session: AsyncSession, patient_id: int
) -> dict[str, Optional[dict[str, Optional[float]]]]:
    """Субшкальные оценки по T0/T1/T2 для пациента."""
    result = await session.execute(
        select(MeasurementPoint)
        .options(selectinload(MeasurementPoint.subscale_scores))
        .where(
            MeasurementPoint.patient_id == patient_id,
            MeasurementPoint.completed_at.isnot(None),
        )
        .order_by(MeasurementPoint.point_type)
    )
    points = list(result.scalars().all())

    output: dict[str, Optional[dict]] = {"T0": None, "T1": None, "T2": None}
    for mp in points:
        output[mp.point_type] = {
            s.subscale_name: float(s.score) if s.score is not None else None
            for s in mp.subscale_scores
        }
    return output


_KDQOL_SUBSCALE_ORDER = [
    "physical_functioning", "role_physical", "pain", "general_health",
    "emotional_wellbeing", "role_emotional", "social_functioning", "energy_fatigue",
    "symptoms", "effects_kidney", "burden_kidney", "work_status",
    "cognitive_function", "quality_social_interaction", "sexual_function",
    "sleep", "social_support", "dialysis_staff_encouragement", "patient_satisfaction",
]


async def kdqol_get_csv_export(
    session: AsyncSession,
    center_id: Optional[str] = None,
) -> str:
    """CSV-экспорт всех субшкальных оценок KDQOL для статистического анализа."""
    from app.users.models import User

    query = (
        select(MeasurementPoint)
        .options(selectinload(MeasurementPoint.subscale_scores))
        .where(MeasurementPoint.completed_at.isnot(None))
        .order_by(MeasurementPoint.patient_id, MeasurementPoint.point_type)
    )

    if center_id is not None:
        ids_result = await session.execute(
            select(User.id).where(User.center_id == center_id)
        )
        patient_ids = [r[0] for r in ids_result.fetchall()]
        if not patient_ids:
            return _kdqol_build_csv([])
        query = query.where(MeasurementPoint.patient_id.in_(patient_ids))

    result = await session.execute(query)
    points = list(result.scalars().all())

    rows = []
    for mp in points:
        score_map = {
            s.subscale_name: float(s.score) if s.score is not None else ""
            for s in mp.subscale_scores
        }
        row = {
            "patient_id": mp.patient_id,
            "point_type": mp.point_type,
            "activated_at": mp.activated_at.isoformat() if mp.activated_at else "",
            "completed_at": mp.completed_at.isoformat() if mp.completed_at else "",
        }
        for sub in _KDQOL_SUBSCALE_ORDER:
            row[sub] = score_map.get(sub, "")
        rows.append(row)

    return _kdqol_build_csv(rows)


def _kdqol_build_csv(rows: list[dict]) -> str:
    output = io.StringIO()
    fieldnames = ["patient_id", "point_type", "activated_at", "completed_at"] + _KDQOL_SUBSCALE_ORDER
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
