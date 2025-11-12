"""CRUD operations for vital measurements."""

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.vitals.models import VitalMeasurement


# 🆕 Создание новой записи витальных показателей пользователя
async def create_measurement(
    session: AsyncSession,
    user_id: int,
    bp_sys: int | None = None,
    bp_dia: int | None = None,
    pulse: int | None = None,
    fluid_intake: float | None = None,
) -> VitalMeasurement:
    """Создаёт запись витальных показателей для пользователя."""

    measurement = VitalMeasurement(
        user_id=user_id,
        bp_sys=bp_sys,
        bp_dia=bp_dia,
        pulse=pulse,
        fluid_intake=fluid_intake,
    )
    session.add(measurement)

    # Отправляем INSERT сразу, чтобы получить значения по умолчанию из БД.
    await session.flush()
    await session.refresh(measurement)
    # Коммит оставляем вызывающему коду, чтобы тестовые транзакции могли делать rollback.

    return measurement


# 📊 Получение последних измерений пользователя за ограниченный период
async def get_user_measurements(
    session: AsyncSession,
    user_id: int,
    days: int = 7,
) -> list[VitalMeasurement]:
    """Возвращает измерения пользователя за последние N дней, отсортированные по времени."""

    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(VitalMeasurement)
        .where(
            VitalMeasurement.user_id == user_id,
            VitalMeasurement.measured_at >= cutoff,
        )
        .order_by(VitalMeasurement.measured_at.desc())
    )

    # Скаляры даёт удобный список ORM-объектов вместо Row.
    result = await session.execute(stmt)
    return result.scalars().all()


# ⏱ Получение самого свежего измерения
async def get_latest_measurement(
    session: AsyncSession,
    user_id: int,
) -> VitalMeasurement | None:
    """Возвращает последнее измерение пользователя (по времени)."""

    stmt = (
        select(VitalMeasurement)
        .where(VitalMeasurement.user_id == user_id)
        .order_by(VitalMeasurement.measured_at.desc())
        .limit(1)
    )

    # first() вернёт None, если записей нет.
    result = await session.execute(stmt)
    return result.scalars().first()


# 🗑 Удаление измерения (под админ-панель или отладку)
async def delete_measurement(session: AsyncSession, measurement_id: int) -> None:
    """Удаляет запись по ID (если потребуется админ-панель)."""

    stmt = delete(VitalMeasurement).where(VitalMeasurement.id == measurement_id)

    # Используем execute, чтобы каскады и триггеры отработали в БД.
    await session.execute(stmt)
    # Flush гарантирует, что удаление попадёт в текущую транзакцию без явного commit.
    await session.flush()
