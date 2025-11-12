"""CRUD operations for vital measurements."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.vitals.models import VitalMeasurement


async def create_measurement(
    session: AsyncSession,
    user_id: int,
    bp_sys: int | None = None,
    bp_dia: int | None = None,
    pulse: int | None = None,
    fluid_intake: float | None = None,
) -> VitalMeasurement:
    """Создаёт запись витальных показателей для пользователя."""

    # Собираем ORM-объект с показателями, оставляя None для неиспользуемых полей.
    measurement = VitalMeasurement(
        user_id=user_id,
        bp_sys=bp_sys,
        bp_dia=bp_dia,
        pulse=pulse,
        fluid_intake=fluid_intake,
    )

    # Добавляем объект в сессию и фиксируем изменения в базе.
    session.add(measurement)
    await session.commit()
    await session.refresh(measurement)

    return measurement


async def get_user_measurements(
    session: AsyncSession,
    user_id: int,
    days: int = 7,
) -> list[VitalMeasurement]:
    """Возвращает измерения пользователя за последние N дней, отсортированные по времени."""

    # Рассчитываем нижнюю границу по времени и выбираем данные из БД.
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(VitalMeasurement)
        .where(
            VitalMeasurement.user_id == user_id,
            VitalMeasurement.measured_at >= cutoff,
        )
        .order_by(VitalMeasurement.measured_at.desc())
    )

    # Получаем ORM-объекты из результата запроса.
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_latest_measurement(
    session: AsyncSession,
    user_id: int,
) -> VitalMeasurement | None:
    """Возвращает последнее измерение пользователя (по времени)."""

    # Берём самую свежую запись по времени измерения.
    stmt = (
        select(VitalMeasurement)
        .where(VitalMeasurement.user_id == user_id)
        .order_by(VitalMeasurement.measured_at.desc())
        .limit(1)
    )

    result = await session.execute(stmt)
    return result.scalars().first()


async def delete_measurement(session: AsyncSession, measurement_id: int) -> None:
    """Удаляет запись по ID (если потребуется админ-панель)."""

    # Формируем DELETE и фиксируем изменения, чтобы удалить запись окончательно.
    stmt = delete(VitalMeasurement).where(VitalMeasurement.id == measurement_id)

    await session.execute(stmt)
    await session.commit()
