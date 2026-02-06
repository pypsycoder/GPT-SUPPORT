from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Optional, Sequence, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.vitals import models, schemas

ModelType = TypeVar("ModelType", bound=models.VitalsBase)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class VitalsCRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: type[ModelType]):
        self.model = model

    async def create(self, session: AsyncSession, obj_in: CreateSchemaType) -> ModelType:
        data: dict[str, Any] = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_none=True)
        db_obj = self.model(**data)
        session.add(db_obj)
        await session.flush()
        await session.refresh(db_obj)
        return db_obj

    async def get(self, session: AsyncSession, obj_id: UUID) -> Optional[ModelType]:
        stmt = select(self.model).where(self.model.id == obj_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        session: AsyncSession,
        *,
        user_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "measured_at desc",
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Sequence[ModelType]:
        stmt = select(self.model)
        if user_id is not None:
            stmt = stmt.where(self.model.user_id == user_id)
        if date_from is not None:
            stmt = stmt.where(self.model.measured_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(self.model.measured_at <= date_to)

        order_expr = self._resolve_order(order_by)
        if order_expr is not None:
            stmt = stmt.order_by(order_expr)

        stmt = stmt.offset(offset).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def update(
        self, session: AsyncSession, obj_id: UUID, obj_in: UpdateSchemaType
    ) -> Optional[ModelType]:
        data: dict[str, Any] = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_none=True)
        if not data:
            return await self.get(session, obj_id)
        stmt = (
            update(self.model)
            .where(self.model.id == obj_id)
            .values(**data)
            .returning(self.model)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, session: AsyncSession, obj_id: UUID) -> None:
        stmt = delete(self.model).where(self.model.id == obj_id)
        await session.execute(stmt)

    def _resolve_order(self, order_by: str) -> Optional[InstrumentedAttribute]:
        direction = order_by.lower().split()
        field_name = direction[0]
        desc_order = len(direction) > 1 and direction[1] == "desc"

        column: Optional[InstrumentedAttribute[Any]] = getattr(self.model, field_name, None)
        if column is None:
            return None
        return column.desc() if desc_order else column.asc()


class BPMeasurementsCRUD(VitalsCRUDBase[models.BPMeasurement, schemas.BPMeasurementCreate, schemas.BPMeasurementUpdate]):
    pass


class PulseMeasurementsCRUD(
    VitalsCRUDBase[models.PulseMeasurement, schemas.PulseMeasurementCreate, schemas.PulseMeasurementUpdate]
):
    pass


class WeightMeasurementsCRUD(
    VitalsCRUDBase[models.WeightMeasurement, schemas.WeightMeasurementCreate, schemas.WeightMeasurementUpdate]
):
    pass


class WaterIntakeCRUD(
    VitalsCRUDBase[models.WaterIntake, schemas.WaterIntakeCreate, schemas.WaterIntakeUpdate]
):
    pass


bp_crud = BPMeasurementsCRUD(models.BPMeasurement)
pulse_crud = PulseMeasurementsCRUD(models.PulseMeasurement)
weight_crud = WeightMeasurementsCRUD(models.WeightMeasurement)
water_crud = WaterIntakeCRUD(models.WaterIntake)

