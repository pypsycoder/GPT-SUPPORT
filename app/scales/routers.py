# ============================================
# Scales API: Эндпоинты психологических шкал
# ============================================
# REST API для прохождения психометрических шкал (HADS, TOBOL, KOP-25A, PSQI).
# Каждая шкала: GET — структура опросника, POST — приём ответов и расчёт результата.
# Также: сводка по всем шкалам (/overview) и история прохождений (/{code}/history).

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.scales.models import ScaleResult
from app.scales.services import (
    calculate_hads_result,
    calculate_kop25a_result,
    calculate_psqi_result,
    calculate_tobol_result,
    get_scale_config,
    save_scale_result,
)
from app.auth.dependencies import get_current_user
from app.users.models import User
from core.db.session import get_async_session

router = APIRouter(tags=["scales"])


# ============================================
#   Pydantic-схемы запросов и ответов
# ============================================

class ScaleOptionOut(BaseModel):
    id: str
    text: str


class ScaleQuestionOut(BaseModel):
    id: str
    text: str
    options: List[ScaleOptionOut]
    # для ТОБОЛ, но опционально, чтобы не ломать HADS/KOP
    section: Optional[str] = None
    section_title: Optional[str] = None

class ScaleDefinitionOut(BaseModel):
    code: str
    title: str
    questions: List[ScaleQuestionOut]


class ScaleAnswerIn(BaseModel):
    question_id: str
    option_id: str


class ScaleSubmitRequest(BaseModel):
    answers: List[ScaleAnswerIn]


class TobolAnswerIn(BaseModel):
    question_id: str
    value: int


class TobolSubmitRequest(BaseModel):
    scale_id: str | None = None
    answers: List[TobolAnswerIn]


class PsqiAnswerIn(BaseModel):
    question_id: str
    value: Any


class PsqiSubmitRequest(BaseModel):
    answers: List[PsqiAnswerIn]


class ScaleResultOut(BaseModel):
    id: UUID
    scale_code: str
    scale_version: str | None
    result: dict
    measured_at: datetime


class ScaleOverviewItem(BaseModel):
    scale_code: str
    scale_name: str
    last_taken_at: datetime | None
    total_score: int | float | None
    summary: str | None


class ScaleHistoryItem(BaseModel):
    id: UUID
    scale_code: str
    measured_at: datetime
    total_score: int | float | None
    summary: str | None




# ============================================
#   HADS — Госпитальная шкала тревоги и депрессии
# ============================================

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


# ============================================
#   TOBOL — Тип отношения к болезни
# ============================================

@router.get("/TOBOL", response_model=ScaleDefinitionOut)
async def get_tobol_definition() -> ScaleDefinitionOut:
    scale_config = get_scale_config("TOBOL")

    questions_for_output: List[ScaleQuestionOut] = []
    for question in scale_config.get("questions", []):
        options = [
            ScaleOptionOut(id=opt["id"], text=opt["text"])
            for opt in question.get("options", [])
        ]

        questions_for_output.append(
            ScaleQuestionOut(
                id=question["id"],
                text=question["text"],
                options=options,
                section=question.get("section"),
                section_title=question.get("section_title"),
            )
        )

    return ScaleDefinitionOut(
        code=scale_config["code"],
        title=scale_config["title"],
        questions=questions_for_output,
    )



@router.post("/HADS/submit", response_model=ScaleResultOut)
async def submit_hads(
    payload: ScaleSubmitRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScaleResultOut:
    """Принимаем ответы по HADS, считаем результат и логируем в БД."""

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
        user_id=user.id,
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
        measured_at=saved.measured_at if isinstance(saved.measured_at, datetime) else datetime.now(timezone.utc),
    )


@router.post("/TOBOL/submit", response_model=ScaleResultOut)
async def submit_tobol(
    payload: TobolSubmitRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScaleResultOut:
    """Принимаем ответы по ТОБОЛ, считаем результат и логируем в БД."""

    if payload.scale_id and payload.scale_id.upper() != "TOBOL":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scale_id должен быть TOBOL",
        )

    try:
        scale_config = get_scale_config("TOBOL")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        result_json, answers_log = calculate_tobol_result(scale_config, payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    saved = await save_scale_result(
        session=session,
        user_id=user.id,
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
        measured_at=saved.measured_at if isinstance(saved.measured_at, datetime) else datetime.now(timezone.utc),
    )


# ============================================
#   KOP-25A — Шкала приверженности лечению
# ============================================

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
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScaleResultOut:
    """Принимаем ответы по KOP-25A, считаем результат и логируем в БД."""

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
        user_id=user.id,
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
        measured_at=saved.measured_at if isinstance(saved.measured_at, datetime) else datetime.now(timezone.utc),
    )


# ============================================
#   PSQI — Питтсбургский опросник качества сна
# ============================================

@router.get("/PSQI")
async def get_psqi_definition():
    """Отдаём структуру опросника PSQI (блоки с вопросами)."""
    scale_config = get_scale_config("PSQI")
    return {
        "code": scale_config["code"],
        "title": scale_config["title"],
        "blocks": scale_config["blocks"],
    }


@router.post("/PSQI/submit", response_model=ScaleResultOut)
async def submit_psqi(
    payload: PsqiSubmitRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScaleResultOut:
    """Принимаем ответы по PSQI, считаем результат и логируем в БД."""

    try:
        scale_config = get_scale_config("PSQI")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        result_json, answers_log = calculate_psqi_result(scale_config, payload.answers)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    saved = await save_scale_result(
        session=session,
        user_id=user.id,
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
        measured_at=saved.measured_at if isinstance(saved.measured_at, datetime) else datetime.now(timezone.utc),
    )


# ============================================
#   Сводка и история прохождений
# ============================================

def _get_scale_title(scale_code: str) -> str:
    try:
        return get_scale_config(scale_code).get("title", scale_code)
    except ValueError:
        return scale_code

# Сводка по шкалам для текущего пользователя
@router.get("/overview", response_model=list[ScaleOverviewItem])
async def get_scales_overview(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[ScaleOverviewItem]:
    stmt = (
        select(ScaleResult)
        .where(ScaleResult.user_id == user.id)
        .order_by(ScaleResult.scale_code, ScaleResult.measured_at.desc())
    )
    res = await session.execute(stmt)
    rows = res.scalars().all()

    latest_by_scale = {}
    for row in rows:
        code = row.scale_code
        if code not in latest_by_scale:
            latest_by_scale[code] = row

    overview: list[ScaleOverviewItem] = []
    for code, row in latest_by_scale.items():
        overview.append(
            {
                "scale_code": row.scale_code,
                "scale_name": _get_scale_title(row.scale_code),
                "last_taken_at": row.measured_at,
                "total_score": (row.result_json or {}).get("total_score"),
                "summary": (row.result_json or {}).get("summary"),
            }
        )

    return overview


# История по одной шкале
@router.get("/{scale_code}/history", response_model=list[ScaleHistoryItem])
async def get_scale_history(
    scale_code: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    limit: int = 20,
) -> list[ScaleHistoryItem]:
    stmt = (
        select(ScaleResult)
        .where(
            ScaleResult.user_id == user.id,
            ScaleResult.scale_code == scale_code,
        )
        .order_by(ScaleResult.measured_at.desc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    rows = res.scalars().all()

    history: list[ScaleHistoryItem] = []
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
