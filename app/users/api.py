# app/users/api.py
# HTTP-ручки для работы с пользователями.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.users import crud
from app.users.schemas import UserPublic

# 👉 ВАЖНО: используем тот же dependency, что и vitals
from core.db.session import get_async_session


router = APIRouter(
    prefix="/patients",
    tags=["patients"],
)


@router.get("/by-token/{patient_token}", response_model=UserPublic)
async def get_patient_by_token(
    patient_token: str,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Найти пациента по patient_token.
    """
    user = await crud.get_user_by_patient_token(session, patient_token=patient_token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пациент с таким токеном не найден",
        )

    return UserPublic.model_validate(user)
