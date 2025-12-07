from __future__ import annotations

from datetime import datetime
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.scales.services import (
    calculate_hads_result,
    get_scale_config,
    save_scale_result,
)
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
    answers: List[ScaleAnswerIn]


class ScaleResultOut(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    scale_code: str
    result: dict
    measured_at: datetime


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

    # TODO: заменить на реальную аутентификацию/авторизацию
    user_id = 1

    try:
        scale_config = get_scale_config("HADS")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # считаем баллы по субшкалам
    result_json, answers_log = calculate_hads_result(scale_config, payload.answers)

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
        scale_code=saved.scale_code,
        result=result_json,
        measured_at=saved.measured_at if isinstance(saved.measured_at, datetime) else datetime.utcnow(),
    )
