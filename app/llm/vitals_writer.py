"""
Запись показателей, разобранных L0, в карту пациента.

Мост между `router_l0.parse_vitals()` и модулем `app/vitals/`. Нужен, потому что
пайплайн показатели только распознаёт, а пишет их роутер — commit по правилам
проекта живёт в слое роутера.

Отмена здесь же: пациент видит в чате кнопку «Отменить», и она должна убирать
ровно те записи, которые создал этот ход. Поэтому `write()` возвращает их
идентификаторы, а роутер кладёт их в кнопку.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.vitals import crud, models, schemas
from app.vitals.service import VitalsService

logger = logging.getLogger("gpt-support-llm.vitals_writer")

# Тип показателя -> (crud, модель). Порядок записи неважен, но набор фиксирован:
# писать сюда что-то за пределами этого словаря L0 не умеет.
_WRITERS: dict[str, tuple[Any, Any]] = {
    "BP": (crud.bp_crud, models.BPMeasurement),
    "PULSE": (crud.pulse_crud, models.PulseMeasurement),
    "WEIGHT": (crud.weight_crud, models.WeightMeasurement),
    "WATER": (crud.water_crud, models.WaterIntake),
}


def _prepare(patient_id: int, item: dict[str, Any]):
    """Разобранный показатель -> схема создания. ``None``, если тип не пишется."""
    kind = str(item.get("type") or "")
    if kind == "BP":
        return VitalsService.prepare_bp_data(
            user_id=patient_id,
            systolic=int(item["systolic"]),
            diastolic=int(item["diastolic"]),
        )
    if kind == "PULSE":
        return VitalsService.prepare_pulse_data(user_id=patient_id, bpm=int(item["value"]))
    if kind == "WEIGHT":
        return VitalsService.prepare_weight_data(user_id=patient_id, weight=float(item["value"]))
    if kind == "WATER":
        return VitalsService.prepare_water_data(user_id=patient_id, volume_ml=int(item["value"]))
    # SLEEP живёт в отдельной схеме sleep_tracker с обязательными полями отхода
    # ко сну и пробуждения — из одной цифры «спал 3 часа» её не собрать.
    return None


async def write(
    session: AsyncSession, patient_id: int, vitals: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Записать показатели. Возвращает ссылки на созданное для кнопки отмены.

    Не коммитит: это делает роутер. Ошибка одного показателя не должна ронять
    ответ пациенту, поэтому каждый пишется отдельно.
    """
    created: list[dict[str, str]] = []
    for item in vitals or []:
        kind = str(item.get("type") or "")
        writer = _WRITERS.get(kind)
        if writer is None:
            continue
        try:
            payload = _prepare(patient_id, item)
            if payload is None:
                continue
            row = await writer[0].create(session, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[vitals_writer] %s не записан patient=%d: %s", kind, patient_id, exc)
            continue
        created.append({"type": kind, "id": str(row.id)})
    return created


async def undo(
    session: AsyncSession, patient_id: int, entries: list[dict[str, str]]
) -> int:
    """Удалить записи, созданные ходом. Возвращает число удалённых.

    Чужие записи не трогает: ``patient_id`` проверяется на каждой.
    """
    removed = 0
    for entry in entries or []:
        writer = _WRITERS.get(str(entry.get("type") or ""))
        if writer is None:
            continue
        try:
            row_id = UUID(str(entry.get("id")))
        except (TypeError, ValueError):
            continue

        model = writer[1]
        result = await session.execute(
            select(model).where(model.id == row_id, model.user_id == patient_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            continue
        await session.delete(row)
        removed += 1
    return removed
