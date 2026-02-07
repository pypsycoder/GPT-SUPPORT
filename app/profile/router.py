# app/profile/router.py
"""API-эндпоинты для профиля пациента."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.profile.schemas import ProfileSummary, ProfileUpdate
from app.profile.service import get_profile_summary, update_profile
from app.users.schemas import UserPublic
from core.db.session import get_async_session

router = APIRouter(tags=["profile"])


@router.get("/summary", response_model=ProfileSummary)
async def get_profile_summary_endpoint(
    patient_token: str,
    session: AsyncSession = Depends(get_async_session),
) -> ProfileSummary:
    """
    Получить полную сводку профиля пациента.

    Включает:
    - Базовые данные (ФИО, возраст, пол, согласия)
    - Сводку витальных показателей (последние измерения)
    - Прогресс обучения
    - Статистику по шкалам
    """
    try:
        return await get_profile_summary(session, patient_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch("/", response_model=UserPublic)
async def update_profile_endpoint(
    patient_token: str,
    data: ProfileUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> UserPublic:
    """
    Обновить данные профиля пациента.

    Можно обновить:
    - full_name (ФИО)
    - age (возраст)
    - gender (пол: "male" или "female")
    """
    try:
        user = await update_profile(session, patient_token, data)
        return UserPublic.model_validate(user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
