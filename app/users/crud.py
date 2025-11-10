# app/users/crud.py — работа с пользователями

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User
from bots.shared.utils import logger


# 📌 Получение пользователя по Telegram ID
async def get_user_by_telegram_id(session: AsyncSession, telegram_id: str):
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ✅ Сохранить пользователя (если нет — создать)
# ВАЖНО: сюда уже передаём session, не открываем новую
async def save_user(session: AsyncSession, telegram_id: str, full_name: str) -> User:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user:
        return user

    user = User(
        telegram_id=telegram_id,
        full_name=full_name,
        consent_bot_use=False,        # пока не нажал кнопку
        consent_personal_data=False,
    )
    session.add(user)
    try:
        await session.flush()  # пусть БД присвоит id
        logger.info(f"[save_user] Зарегистрирован: {telegram_id} | {full_name}")
    except IntegrityError as e:
        logger.warning(f"[save_user] Ошибка вставки {telegram_id}: {e}")
    return user


# 🔄 Обновить согласие пользователя
async def update_user_consent(session: AsyncSession, telegram_id: str, consent: bool) -> None:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        user.consent_bot_use = consent
        user.consent_personal_data = consent
        await session.commit()
        logger.info(f"[consent] Обновлено согласие для {telegram_id}: {consent}")
