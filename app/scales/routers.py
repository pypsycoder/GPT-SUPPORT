# ============================================
# Scales API: Эндпоинты психологических шкал
# ============================================
# REST API для прохождения психометрических шкал (HADS, KOP-25A, PSQI, PSS-10, WCQ).
# Каждая шкала: GET — структура опросника, POST — приём ответов и расчёт результата.
# Также: сводка по всем шкалам (/overview) и история прохождений (/{code}/history).

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.scales.models import MeasurementPoint, ScaleResult
from app.scales.services import (
    calculate_hads_result,
    calculate_kop25a_result,
    calculate_psqi_result,
    calculate_pss10_result,
    calculate_wcq_lazarus_result,
    get_scale_config,
    kdqol_activate_point,
    kdqol_get_csv_export,
    kdqol_get_patient_points,
    kdqol_get_patient_scores,
    kdqol_get_pending_point,
    kdqol_process_submit,
    save_scale_result,
)
from app.auth.dependencies import get_current_researcher, get_current_user
from app.researchers.models import Researcher
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
#   PSS-10 — Шкала воспринимаемого стресса (ШВС-10)
# ============================================

@router.get("/PSS10", response_model=ScaleDefinitionOut)
async def get_pss10_definition() -> ScaleDefinitionOut:
    """Отдаём структуру шкалы ШВС-10 (PSS-10) без баллов."""

    scale_config = get_scale_config("PSS10")

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


@router.post("/PSS10/submit", response_model=ScaleResultOut)
async def submit_pss10(
    payload: ScaleSubmitRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScaleResultOut:
    """Принимаем ответы по ШВС-10, считаем результат и логируем в БД."""

    try:
        scale_config = get_scale_config("PSS10")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        result_json, answers_log = calculate_pss10_result(scale_config, payload.answers)
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
#   WCQ (Лазарус) — Опросник совладающего поведения
# ============================================

@router.get("/WCQ_LAZARUS", response_model=ScaleDefinitionOut)
async def get_wcq_lazarus_definition() -> ScaleDefinitionOut:
    """Отдаём структуру опросника WCQ (Лазарус) без баллов."""

    scale_config = get_scale_config("WCQ_LAZARUS")

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


@router.post("/WCQ_LAZARUS/submit", response_model=ScaleResultOut)
async def submit_wcq_lazarus(
    payload: ScaleSubmitRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> ScaleResultOut:
    """Принимаем ответы по WCQ (Лазарус), считаем субшкалы и сохраняем в БД.

    Глобальный балл не используется — только 8 субшкальных сумм +
    нормализованные баллы + adaptive_ratio.
    Пациенту возвращается только patient_message.
    """

    try:
        scale_config = get_scale_config("WCQ_LAZARUS")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        result_json, answers_log = calculate_wcq_lazarus_result(scale_config, payload.answers)
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


# ============================================================
# KDQOL-SF 1.3 — Pydantic schemas
# ============================================================

class KdqolAnswerIn(BaseModel):
    question_id: str
    answer_value: float


class KdqolSubmitRequest(BaseModel):
    measurement_point_id: int
    responses: List[KdqolAnswerIn]


class KdqolSubmitResponse(BaseModel):
    success: bool
    feedback_module: Optional[str] = None


class ActivatePointRequest(BaseModel):
    point_type: Literal["T0", "T1", "T2"]
    scale_code: Literal["KDQOL_SF", "WCQ_LAZARUS", "KOP_25A"] = "KDQOL_SF"


class MeasurementPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    scale_code: str
    point_type: str
    activated_at: datetime
    activated_by: Optional[int]
    completed_at: Optional[datetime]
    is_completed: bool

    @classmethod
    def from_mp(cls, mp: MeasurementPoint) -> "MeasurementPointOut":
        return cls(
            id=mp.id,
            patient_id=mp.patient_id,
            scale_code=mp.scale_code,
            point_type=mp.point_type,
            activated_at=mp.activated_at,
            activated_by=mp.activated_by,
            completed_at=mp.completed_at,
            is_completed=mp.completed_at is not None,
        )


class KdqolPatientScoresOut(BaseModel):
    T0: Optional[dict] = None
    T1: Optional[dict] = None
    T2: Optional[dict] = None


# ============================================================
# KDQOL-SF 1.3 — Patient router  (prefix /patient/kdqol)
# ============================================================

import json
from pathlib import Path

_KDQOL_QUESTIONS_PATH = Path(__file__).resolve().parent / "resources" / "kdqol_sf_structure.json"
with _KDQOL_QUESTIONS_PATH.open(encoding="utf-8") as _f:
    _KDQOL_QUESTIONS_JSON: dict = json.load(_f)

kdqol_patient_router = APIRouter(prefix="/patient/kdqol", tags=["kdqol"])


@kdqol_patient_router.get("/pending", response_model=Optional[MeasurementPointOut])
async def kdqol_pending(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Вернуть активированную незавершённую точку измерения или null."""
    mp = await kdqol_get_pending_point(session, user.id)
    return MeasurementPointOut.from_mp(mp) if mp else None


@kdqol_patient_router.get("/questions")
async def kdqol_questions(_user: User = Depends(get_current_user)):
    """Полная структура вопросов KDQOL-SF из JSON."""
    return _KDQOL_QUESTIONS_JSON


@kdqol_patient_router.post("/submit", response_model=KdqolSubmitResponse)
async def kdqol_submit(
    payload: KdqolSubmitRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Сохранить ответы, посчитать субшкалы, завершить точку измерения."""
    result = await kdqol_process_submit(
        session=session,
        patient_id=user.id,
        measurement_point_id=payload.measurement_point_id,
        responses=payload.responses,
    )
    return KdqolSubmitResponse(**result)


_PATIENT_SHOWN_SUBSCALES = {
    "symptoms",
    "burden_kidney",
    "quality_social_interaction",
    "dialysis_staff_encouragement",
    "emotional_wellbeing",
    "energy_fatigue",
}


@kdqol_patient_router.get("/latest-scores")
async def kdqol_latest_scores(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Субшкальные оценки по последней завершённой точке измерения пациента."""
    result = await session.execute(
        select(MeasurementPoint)
        .options(selectinload(MeasurementPoint.subscale_scores))
        .where(
            MeasurementPoint.patient_id == user.id,
            MeasurementPoint.completed_at.isnot(None),
        )
        .order_by(MeasurementPoint.completed_at.desc())
        .limit(1)
    )
    mp = result.scalar_one_or_none()
    if mp is None:
        return {"scores": None}
    scores = {
        s.subscale_name: float(s.score) if s.score is not None else None
        for s in mp.subscale_scores
        if s.subscale_name in _PATIENT_SHOWN_SUBSCALES
    }
    return {"point_type": mp.point_type, "scores": scores}


# ============================================================
# KDQOL-SF 1.3 — Researcher router  (prefix /researcher)
# ============================================================

kdqol_researcher_router = APIRouter(prefix="/researcher", tags=["kdqol"])


@kdqol_researcher_router.post(
    "/patients/{patient_id}/measurement-points",
    response_model=MeasurementPointOut,
    status_code=201,
)
async def kdqol_activate(
    patient_id: int,
    body: ActivatePointRequest,
    researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Активировать точку измерения T0/T1/T2 для пациента."""
    mp = await kdqol_activate_point(session, patient_id, researcher.id, body.point_type, body.scale_code)
    await session.commit()
    await session.refresh(mp)
    return MeasurementPointOut.from_mp(mp)


@kdqol_researcher_router.get(
    "/patients/{patient_id}/measurement-points",
    response_model=List[MeasurementPointOut],
)
async def kdqol_list_points(
    patient_id: int,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Список всех точек измерения пациента с их статусами."""
    points = await kdqol_get_patient_points(session, patient_id)
    return [MeasurementPointOut.from_mp(mp) for mp in points]


@kdqol_researcher_router.get(
    "/patients/{patient_id}/kdqol-scores",
    response_model=KdqolPatientScoresOut,
)
async def kdqol_scores(
    patient_id: int,
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """Субшкальные оценки KDQOL по T0/T1/T2."""
    scores = await kdqol_get_patient_scores(session, patient_id)
    return KdqolPatientScoresOut(**scores)


@kdqol_researcher_router.get("/kdqol-export")
async def kdqol_export(
    center_id: Optional[str] = Query(None, description="UUID диализного центра"),
    _researcher: Researcher = Depends(get_current_researcher),
    session: AsyncSession = Depends(get_async_session),
):
    """CSV-экспорт субшкальных оценок KDQOL всех пациентов."""
    csv_content = await kdqol_get_csv_export(session, center_id=center_id)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kdqol_export.csv"},
    )
