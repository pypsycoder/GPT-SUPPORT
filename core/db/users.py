# database/users.py

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.db.models import User

# get_user_by_telegram_id
# Берёт пользователя по tg_id, используя уже открытую сессию
async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int):
    stmt = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
