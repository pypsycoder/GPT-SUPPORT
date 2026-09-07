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

from app.dialysis.models import Center, DialysisSchedule
from app.dialysis.schemas import DialysisWindow

if TYPE_CHECKING:
    pass


# Фолбэк-часы смен, если у центра пациента они почему-то не заданы
# (или центр не привязан). Совпадают с server_default колонок ``centers``.
DEFAULT_SHIFT_TIMES: dict[str, tuple[datetime.time, datetime.time]] = {
    "morning": (datetime.time(8, 0), datetime.time(11, 0)),
    "afternoon": (datetime.time(13, 0), datetime.time(17, 0)),
    "evening": (datetime.time(18, 0), datetime.time(21, 0)),
}


async def _active_schedule_for_date(
    session: AsyncSession,
    patient_id: int,
    date: datetime.date,
) -> DialysisSchedule | None:
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
    return result.scalar_one_or_none()


async def is_dialysis_day(
    session: AsyncSession,
    patient_id: int,
    date: datetime.date,
) -> bool | None:
    """
    Возвращает True/False если расписание на дату найдено,
    None если расписание на эту дату не найдено.
    """
    schedule = await _active_schedule_for_date(session, patient_id, date)
    if schedule is None:
        return None
    # isoweekday(): 1=Пн, 7=Вс
    return date.isoweekday() in schedule.weekdays


async def get_dialysis_window(
    session: AsyncSession,
    *,
    patient_id: int,
    date: datetime.date,
) -> DialysisWindow | None:
    """Окно диализа для дня: смена пациента + часы этой смены в его центре.

    Возвращает ``None``, если день не диализный или расписание не найдено.
    Часы берутся из ``centers.<shift>_{start,end}``; при отсутствии центра или
    значений — из :data:`DEFAULT_SHIFT_TIMES`.
    """
    schedule = await _active_schedule_for_date(session, patient_id, date)
    if schedule is None:
        return None
    if date.isoweekday() not in (schedule.weekdays or []):
        return None

    shift = str(schedule.shift)

    # Импорт здесь, чтобы не тянуть users-модель в модуль-хелпер на уровне файла.
    from app.users.models import User

    center_id = (
        await session.execute(select(User.center_id).where(User.id == patient_id))
    ).scalar_one_or_none()

    start: datetime.time | None = None
    end: datetime.time | None = None
    if center_id is not None:
        center = (
            await session.execute(select(Center).where(Center.id == center_id))
        ).scalar_one_or_none()
        if center is not None:
            start = getattr(center, f"{shift}_start", None)
            end = getattr(center, f"{shift}_end", None)

    if start is None or end is None:
        start, end = DEFAULT_SHIFT_TIMES.get(shift, (None, None))
    if start is None or end is None:
        return None

    return DialysisWindow(
        shift=shift,
        start=start.strftime("%H:%M"),
        end=end.strftime("%H:%M"),
    )
