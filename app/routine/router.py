from __future__ import annotations

"""API-роутер для модуля рутины (d230).

Эндпоинты:
- GET/POST /routine/baseline       — получение и обновление baseline-опросника.
- GET/POST /routine/plan          — получение плана по дате и сохранение (планер).
- GET/POST /routine/verification  — получение/сохранение верификации.
- GET /routine/metrics            — выгрузка дневных метрик для анализа.
"""

import datetime as dt
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.dialysis.service import is_dialysis_day
from app.routine import crud, schemas, service
from app.users.models import User
from core.db.session import get_async_session


router = APIRouter(prefix="/routine", tags=["routine"])


# --- Baseline ---


@router.get("/baseline", response_model=schemas.BaselineRoutineRead)
async def get_baseline_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Получить актуальный baseline-опросник пациента.

    Если baseline ещё не заполнялся, возвращает 404.
    """
    baseline = await crud.get_active_baseline(session, patient_id=user.id)
    if baseline is None:
        raise HTTPException(status_code=404, detail="Baseline ещё не заполнен")
    return baseline


@router.post("/baseline", response_model=schemas.BaselineRoutineRead)
async def create_or_update_baseline_me(
    payload: schemas.BaselineRoutineCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Создать baseline при онбординге или обновить (создать новую версию)."""
    now = dt.datetime.now(dt.timezone.utc)
    baseline = await service.RoutineService.upsert_baseline(
        session,
        patient_id=user.id,
        payload=payload,
        now=now,
    )
    await session.commit()
    await session.refresh(baseline)
    return baseline


# --- Планер ---


@router.get("/plan", response_model=schemas.DailyPlanRead)
async def get_plan_by_date_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    qdate: date = Query(..., alias="date", description="Дата плана (YYYY-MM-DD)"),
):
    """Получить план на дату.

    Если план существует — возвращается сохранённый план.
    Если нет — формируется предзаполненный шаблон на основе baseline и dialysis_day.
    В случае отсутствия baseline возвращается 404.
    """
    plan, template_data = await service.RoutineService.get_or_build_plan(
        session,
        patient_id=user.id,
        plan_date=qdate,
    )
    if plan is not None:
        # Если в сохранённом плане пустые template_activities/added_from_pool (старая запись),
        # подставляем шаблон из baseline, чтобы UI и следующее сохранение получили полные данные.
        ta = getattr(plan, "template_activities", None) or {}
        ap = getattr(plan, "added_from_pool", None) or {}
        if not ta or not ap:
            fill = await service.RoutineService.get_template_data(
                session, patient_id=user.id, plan_date=qdate
            )
            if fill:
                merged = type("TmpPlan", (), {})()
                merged.id = plan.id
                merged.patient_id = plan.patient_id
                merged.plan_date = plan.plan_date
                merged.created_at = plan.created_at
                merged.dialysis_day = plan.dialysis_day if plan.dialysis_day is not None else fill["dialysis_day"]
                merged.template_activities = ta if ta else fill["template_activities"]
                merged.added_from_pool = ap if ap else fill["added_from_pool"]
                merged.custom_activities = getattr(plan, "custom_activities", None)
                if merged.custom_activities is None:
                    merged.custom_activities = [None, None, None, None, None]
                merged.edit_count = getattr(plan, "edit_count", 0)
                merged.retrospective_days = getattr(plan, "retrospective_days", None)
                # #region agent log
                import json as _json
                with open(r"d:\PROJECT\GPT-SUPPORT\.cursor\debug.log", "a", encoding="utf-8") as _f:
                    _f.write(_json.dumps({"location": "routine/router.py:get_plan_by_date_me", "message": "returning hydrated plan", "data": {"template_keys": list(merged.template_activities.keys()), "added_keys": list(merged.added_from_pool.keys())}, "hypothesisId": "post-fix", "timestamp": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)}, ensure_ascii=False) + "\n")
                # #endregion
                return merged  # type: ignore[return-value]
        return plan

    if template_data is None:
        raise HTTPException(status_code=404, detail="Baseline ещё не заполнен")

    # Строим временный объект, имитирующий ORM-модель, чтобы удовлетворить response_model
    dialysis_day_flag = await is_dialysis_day(session, patient_id=user.id, date=qdate)
    fake = type("TmpPlan", (), {})()
    fake.id = None
    fake.patient_id = user.id
    fake.plan_date = qdate
    fake.created_at = dt.datetime.now(dt.timezone.utc)
    fake.dialysis_day = dialysis_day_flag
    fake.template_activities = template_data.get("template_activities")
    fake.added_from_pool = template_data.get("added_from_pool")
    fake.custom_activities = template_data.get("custom_activities")
    fake.edit_count = 0
    fake.retrospective_days = 0
    # #region agent log
    import json as _json
    _ta = template_data.get("template_activities") or {}
    _ap = template_data.get("added_from_pool") or {}
    with open(r"d:\PROJECT\GPT-SUPPORT\.cursor\debug.log", "a", encoding="utf-8") as _f:
        _f.write(_json.dumps({"location": "routine/router.py:get_plan_by_date_me", "message": "returning draft", "data": {"template_keys": list(_ta.keys()), "added_keys": list(_ap.keys())}, "hypothesisId": "H1,H5", "timestamp": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)}, ensure_ascii=False) + "\n")
    # #endregion
    return fake  # type: ignore[return-value]


@router.post("/plan", response_model=schemas.DailyPlanRead)
async def save_plan_me(
    payload: schemas.DailyPlanCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Создать или перезаписать план на дату.

    Ограничение: один план на (patient_id, plan_date). При повторном сохранении edit_count увеличивается.
    """
    # #region agent log
    import json as _json
    _ta = (payload.template_activities or {}).keys()
    _ap = (payload.added_from_pool or {}).keys()
    with open(r"d:\PROJECT\GPT-SUPPORT\.cursor\debug.log", "a", encoding="utf-8") as _f:
        _f.write(_json.dumps({"location": "routine/router.py:save_plan_me", "message": "payload received", "data": {"template_keys": list(_ta), "added_keys": list(_ap)}, "hypothesisId": "H3,H4", "timestamp": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)}, ensure_ascii=False) + "\n")
    # #endregion
    today = dt.datetime.now(dt.timezone.utc).date()
    if (today - payload.plan_date).days > 3:
        raise HTTPException(status_code=400, detail="Нельзя вносить план более чем за 3 дня назад")

    plan = await service.RoutineService.save_plan(
        session,
        patient_id=user.id,
        payload=payload,
    )
    await session.commit()
    await session.refresh(plan)
    return plan


# --- Верификация ---


@router.get("/verification", response_model=schemas.DailyVerificationRead)
async def get_verification_by_date_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    qdate: date = Query(..., alias="date", description="Дата дня (YYYY-MM-DD)"),
):
    """Получить верификацию за дату, если она существует."""
    ver = await crud.get_verification_by_date(
        session,
        patient_id=user.id,
        verification_date=qdate,
    )
    if ver is None:
        raise HTTPException(status_code=404, detail="Верификация за эту дату не найдена")
    return ver


@router.post("/verification", response_model=schemas.DailyVerificationRead)
async def save_verification_me(
    payload: schemas.DailyVerificationCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Создать или обновить верификацию за день.

    day_control_score — обязательное поле, остальные блоки могут быть пустыми.
    """
    today = dt.datetime.now(dt.timezone.utc).date()
    if (today - payload.verification_date).days > 3:
        raise HTTPException(
            status_code=400,
            detail="Нельзя вносить верификацию более чем за 3 дня назад",
        )

    ver = await service.RoutineService.save_verification(
        session,
        patient_id=user.id,
        payload=payload,
    )
    await session.commit()
    await session.refresh(ver)
    return ver


# --- Метрики / отчётность ---


@router.get("/metrics", response_model=list[schemas.DailyRoutineMetrics])
async def get_routine_metrics_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    """Выгрузка дневных метрик по пациенту для аналитики (LMM и др.)."""
    # Заготовка: простая выборка по диапазону дат.
    # При необходимости можно оптимизировать и вынести в отдельный репозиторий.
    if date_from is None or date_to is None:
        today = dt.date.today()
        date_to = today
        date_from = today - dt.timedelta(days=30)

    # Для простоты: один baseline на период.
    baseline = await crud.get_active_baseline(session, patient_id=user.id)
    planning_time = baseline.planning_time if baseline else None

    days: list[schemas.DailyRoutineMetrics] = []
    current = date_from
    assert date_to is not None
    while current <= date_to:
        plan = await crud.get_plan_by_date(session, patient_id=user.id, plan_date=current)
        ver = await crud.get_verification_by_date(
            session,
            patient_id=user.id,
            verification_date=current,
        )
        dialysis_flag = await is_dialysis_day(session, patient_id=user.id, date=current)
        metrics = service.RoutineService.compute_metrics_for_day(
            baseline_planning_time=planning_time,
            plan_date=current,
            dialysis_day=dialysis_flag,
            plan=plan,
            verification=ver,
        )
        days.append(metrics)
        current += dt.timedelta(days=1)

    return days


