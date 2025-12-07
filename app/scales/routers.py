from __future__ import annotations

from datetime import datetime
from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.scales.services import (
    calculate_hads_result,
    calculate_kop25a_result,
    get_scale_config,
    save_scale_result,
)
from app.users.crud import get_user_by_patient_token
from core.db.session import get_async_session

router = APIRouter(prefix="", tags=["scales"])


class ScaleOptionOut(BaseModel):
    id: str
    text: str


class ScaleQuestionOut(BaseModel):
    id: str
    text: str
    options: List[ScaleOptionOut]


class ScaleDefinitionOut(BaseModel):
    code: str
    title: str
    questions: List[ScaleQuestionOut]


class ScaleAnswerIn(BaseModel):
    question_id: str
    option_id: str


class ScaleSubmitRequest(BaseModel):
    patient_token: str
    answers: List[ScaleAnswerIn]


class ScaleResultOut(BaseModel):
    id: UUID
    scale_code: str
    scale_version: str | None
    result: dict
    measured_at: datetime


async def resolve_user_id_by_patient_token(
    session: AsyncSession, patient_token: str
) -> int:
    """
    Возвращает внутренний user_id по patient_token.

    Если пользователь не найден — выбрасывает 404.
    """

    user = await get_user_by_patient_token(session=session, patient_token=patient_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пациент с таким токеном не найден",
        )

    return user.id


@router.get("/HADS", response_model=ScaleDefinitionOut)
async def get_hads_definition() -> ScaleDefinitionOut:
    """Отдаём структуру шкалы HADS без баллов."""

    # получаем конфиг шкалы
    scale_config = get_scale_config("HADS")

    # скрываем значения баллов
    questions_for_output: List[ScaleQuestionOut] = []
    for question in scale_config.get("questions", []):
        options = [ScaleOptionOut(id=opt["id"], text=opt["text"]) for opt in question["options"]]
        questions_for_output.append(
            ScaleQuestionOut(id=question["id"], text=question["text"], options=options)
        )

    return ScaleDefinitionOut(
        code=scale_config["code"],
        title=scale_config["title"],
        questions=questions_for_output,
    )


@router.post("/HADS/submit", response_model=ScaleResultOut)
async def submit_hads(
    payload: ScaleSubmitRequest,
    session: AsyncSession = Depends(get_async_session),
) -> ScaleResultOut:
    """Принимаем ответы по HADS, считаем результат и логируем в БД."""

    user_id = await resolve_user_id_by_patient_token(
        session=session, patient_token=payload.patient_token
    )

    try:
        scale_config = get_scale_config("HADS")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # считаем баллы по субшкалам
    try:
        result_json, answers_log = calculate_hads_result(scale_config, payload.answers)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # сохраняем результат в БД
    saved = await save_scale_result(
        session=session,
        user_id=user_id,
        scale_code=scale_config["code"],
        scale_version=scale_config.get("version", ""),
        result_json=result_json,
        answers_log=answers_log,
    )

    return ScaleResultOut(
        id=saved.id,
        scale_code=saved.scale_code,
        scale_version=saved.scale_version,
        result=result_json,
        measured_at=saved.measured_at if isinstance(saved.measured_at, datetime) else datetime.utcnow(),
    )


@router.get("/KOP25A", response_model=ScaleDefinitionOut)
async def get_kop25a_definition() -> ScaleDefinitionOut:
    scale_config = get_scale_config("KOP25A")

    questions_for_output: List[ScaleQuestionOut] = []
    for question in scale_config.get("questions", []):
        options = [ScaleOptionOut(id=opt["id"], text=opt["text"]) for opt in question["options"]]
        questions_for_output.append(
            ScaleQuestionOut(
                id=question["id"],
                text=question["text"],
                options=options,
            )
        )

    return ScaleDefinitionOut(
        code=scale_config["code"],
        title=scale_config["title"],
        questions=questions_for_output,
    )


@router.post("/KOP25A/submit", response_model=ScaleResultOut)
async def submit_kop25a(
    payload: ScaleSubmitRequest,
    session: AsyncSession = Depends(get_async_session),
) -> ScaleResultOut:
    """Принимаем ответы по KOP-25A, считаем результат и логируем в БД."""

    user_id = await resolve_user_id_by_patient_token(
        session=session, patient_token=payload.patient_token
    )

    try:
        scale_config = get_scale_config("KOP25A")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        result_json, answers_log = calculate_kop25a_result(
            scale_config,
            payload.answers,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    saved = await save_scale_result(
        session=session,
        user_id=user_id,
        scale_code=scale_config["code"],
        scale_version=scale_config.get("version", ""),
        result_json=result_json,
        answers_log=answers_log,
    )

    return ScaleResultOut(
        id=saved.id,
        scale_code=saved.scale_code,
        scale_version=saved.scale_version,
        result=result_json,
        measured_at=saved.measured_at if isinstance(saved.measured_at, datetime) else datetime.utcnow(),
    )



from sqlalchemy import select
from app.scales.models import ScaleResult  # имя модели проверить

# Сводка по шкалам для токена
@router.get("/api/v1/scales/overview")
async def get_scales_overview(
    patient_token: str,
    session: AsyncSession = Depends(get_async_session),
) -> list[dict[str, Any]]:
    user_id = await resolve_user_id_by_patient_token(session, patient_token)

    stmt = (
        select(ScaleResult)
        .where(ScaleResult.user_id == user_id)
        .order_by(ScaleResult.scale_code, ScaleResult.measured_at.desc())
    )
    res = await session.execute(stmt)
    rows = res.scalars().all()

    latest_by_scale = {}
    for row in rows:
        code = row.scale_code
        if code not in latest_by_scale:
            latest_by_scale[code] = row

    overview: list[dict[str, Any]] = []
    for code, row in latest_by_scale.items():
        overview.append(
            {
                "scale_code": row.scale_code,
                "scale_name": row.scale_code,  # можно потом подтянуть красивые имена
                "last_taken_at": row.measured_at,
                "total_score": (row.result_json or {}).get("total_score"),
                "summary": (row.result_json or {}).get("summary"),
            }
        )

    return overview


# История по одной шкале
@router.get("/api/v1/scales/{scale_code}/history")
async def get_scale_history(
    scale_code: str,
    patient_token: str,
    limit: int = 20,
    session: AsyncSession = Depends(get_async_session),
) -> list[dict[str, Any]]:
    user_id = await resolve_user_id_by_patient_token(session, patient_token)

    stmt = (
        select(ScaleResult)
        .where(
            ScaleResult.user_id == user_id,
            ScaleResult.scale_code == scale_code,
        )
        .order_by(ScaleResult.measured_at.desc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    rows = res.scalars().all()

    history: list[dict[str, Any]] = []
    for row in rows:
        result = row.result_json or {}
        history.append(
            {
                "id": row.id,
                "scale_code": row.scale_code,
                "measured_at": row.measured_at,
                "total_score": result.get("total_score"),
                "summary": result.get("summary"),
            }
        )

    return history
