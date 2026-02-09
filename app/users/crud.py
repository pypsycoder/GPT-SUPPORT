"""CRUD-функции для работы с пользователями."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User
from bots.shared.utils import logger


# get_user_by_telegram_id
async def get_user_by_telegram_id(
    session: AsyncSession,
    telegram_id: str,
) -> Optional[User]:
    """
    Найти пользователя по telegram_id.

    Ничего не коммитит — просто читает из БД.
    """
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    logger.debug("[users][crud] get_user_by_telegram_id(%s) -> %s", telegram_id, user.id if user else None)
    return user

# save_user
async def save_user(
    session: AsyncSession,
    *,
    telegram_id: str,
    full_name: Optional[str] = None,
) -> User:
    """
    Получить или создать пользователя по telegram_id.

    ⚙ Поведение:
    - если пользователь уже есть — при необходимости обновляет full_name и коммитит изменения;
    - если пользователя нет — создаёт, коммитит и возвращает.

    Важно: функция САМА делает commit и refresh,
    чтобы работать нормально в сценарии с `async_session_factory()` внутри хендлеров бота.
    """
    # 1) пробуем найти существующего пользователя
    user = await get_user_by_telegram_id(session, telegram_id=telegram_id)
    if user is not None:
        updated = False

        # мягко обновляем ФИО, если оно поменялось
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            updated = True

        if updated:
            await session.commit()
            await session.refresh(user)
            logger.info(
                "[users][crud] updated user %s (telegram_id=%s, full_name=%r)",
                user.id,
                telegram_id,
                full_name,
            )
        else:
            logger.debug(
                "[users][crud] user %s (telegram_id=%s) already up-to-date",
                user.id,
                telegram_id,
            )

        return user

    # 2) пользователя нет — создаём нового
    user = User(
        telegram_id=telegram_id,
        full_name=full_name,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    logger.info(
        "[users][crud] created user %s (telegram_id=%s, full_name=%r)",
        user.id,
        telegram_id,
        full_name,
    )
    return user


# update_user_profile
async def update_user_profile(
    session: AsyncSession,
    user: User,
    *,
    full_name: Optional[str] = None,
    age: Optional[int] = None,
    gender: Optional[str] = None,
) -> User:
    """
    Обновить профиль пользователя (ФИО, возраст, пол).

    Принимает уже найденного пользователя и обновляет только те поля,
    которые переданы (не None).

    Коммитит изменения и возвращает обновленного пользователя.
    """
    updated = False

    if full_name is not None and user.full_name != full_name:
        user.full_name = full_name
        updated = True

    if age is not None and user.age != age:
        user.age = age
        updated = True

    if gender is not None and user.gender != gender:
        user.gender = gender
        updated = True

    if updated:
        await session.commit()
        await session.refresh(user)
        logger.info(
            "[users][crud] updated profile for user %s (full_name=%r, age=%r, gender=%r)",
            user.id,
            full_name,
            age,
            gender,
        )
    else:
        logger.debug(
            "[users][crud] profile for user %s already up-to-date",
            user.id,
        )

    return user
