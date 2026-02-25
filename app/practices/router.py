from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.practices.models import StandalonePractice as Practice, PracticeCompletion
from app.practices.schemas import CompleteIn, CompleteOut, PracticeOut
from app.users.models import User
from core.db.session import get_async_session

router = APIRouter(tags=["practices"])


@router.get("/practices", response_model=List[PracticeOut])
async def list_practices(
    module_id: Optional[str] = Query(default=None, description="Фильтр по module_id (напр. '01')"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Список активных практик, опционально отфильтрованных по модулю."""
    stmt = select(Practice).where(Practice.is_active.is_(True)).order_by(Practice.module_id)
    if module_id is not None:
        stmt = stmt.where(Practice.module_id == module_id)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/practices/{practice_id}", response_model=PracticeOut)
async def get_practice(
    practice_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Получить одну практику по id."""
    practice = await session.get(Practice, practice_id)
    if practice is None or not practice.is_active:
        raise HTTPException(status_code=404, detail="Практика не найдена")
    return practice


@router.post("/practices/{practice_id}/complete", response_model=CompleteOut)
async def complete_practice(
    practice_id: str,
    body: CompleteIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Записать выполнение практики пациентом."""
    practice = await session.get(Practice, practice_id)
    if practice is None or not practice.is_active:
        raise HTTPException(status_code=404, detail="Практика не найдена")

    completion = PracticeCompletion(
        patient_id=user.id,
        practice_id=practice_id,
        mood_after=body.mood_after,
    )
    session.add(completion)
    await session.commit()
    await session.refresh(completion)

    return CompleteOut(
        success=True,
        practice_id=practice_id,
        completed_at=completion.completed_at,
    )
