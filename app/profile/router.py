# app/profile/router.py
"""API-эндпоинты для профиля пациента."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.profile.schemas import ProfileSummary, ProfileUpdate
from app.profile.service import get_profile_summary, update_profile
from app.users.schemas import UserPublic
from app.auth.dependencies import get_current_user
from app.users.models import User
from core.db.session import get_async_session

router = APIRouter(tags=["profile"])


@router.get("/summary", response_model=ProfileSummary)
async def get_profile_summary_endpoint(
    user: User = Depends(get_current_user),
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
    import logging
    logger = logging.getLogger("gpt-support")
    
    try:
        logger.info(f"[profile] Getting summary for user {user.id}")
        result = await get_profile_summary(session, user)
        logger.info(f"[profile] Summary retrieved successfully for user {user.id}")
        return result
    except ValueError as exc:
        logger.error(f"[profile] ValueError: {exc}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(f"[profile] Unexpected error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {exc}",
        ) from exc


@router.patch("/update", response_model=UserPublic)
async def update_profile_endpoint(
    data: ProfileUpdate,
    user: User = Depends(get_current_user),
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
        updated_user = await update_profile(session, user, data)
        return UserPublic.model_validate(updated_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
