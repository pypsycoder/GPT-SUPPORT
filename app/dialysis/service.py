# ============================================
# Dialysis Service: is_dialysis_day и вспомогательная логика
# ============================================
# Использование: при появлении модуля Sleep Tracker (или записи сна по дате)
# импортировать: from app.dialysis import is_dialysis_day
# и для каждой записи/отчёта по дате вызывать:
#   dialysis_day = await is_dialysis_day(session, patient_id=user.id, date=target_date)
# Результат True/False/None сохранять в поле dialysis_day или включать в ответ API.

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dialysis.models import DialysisSchedule

if TYPE_CHECKING:
    pass


async def is_dialysis_day(
    session: AsyncSession,
    patient_id: int,
    date: datetime.date,
) -> bool | None:
    """
    Возвращает True/False если расписание на дату найдено,
    None если расписание на эту дату не найдено.
    """
    stmt = (
        select(DialysisSchedule)
        .where(DialysisSchedule.patient_id == patient_id)
        .where(DialysisSchedule.valid_from <= date)
        .where(
            or_(
                DialysisSchedule.valid_to.is_(None),
                DialysisSchedule.valid_to >= date,
            )
        )
    )
    result = await session.execute(stmt)
    schedule = result.scalar_one_or_none()
    if schedule is None:
        return None
    # isoweekday(): 1=Пн, 7=Вс
    return date.isoweekday() in schedule.weekdays
