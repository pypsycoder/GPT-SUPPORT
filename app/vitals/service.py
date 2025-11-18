from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.vitals import schemas


class VitalsService:
    @staticmethod
    def normalize_measured_at(measured_at: Optional[datetime]) -> datetime:
        if measured_at is None:
            return datetime.now(timezone.utc)
        if measured_at.tzinfo is None:
            return measured_at.replace(tzinfo=timezone.utc)
        return measured_at.astimezone(timezone.utc)

    @staticmethod
    def validate_bp(systolic: int, diastolic: int, pulse: Optional[int] = None) -> None:
        if not 50 <= systolic <= 250:
            raise ValueError("Недопустимое значение систолического давления")
        if not 30 <= diastolic <= 150:
            raise ValueError("Недопустимое значение диастолического давления")
        if pulse is not None and not 30 <= pulse <= 250:
            raise ValueError("Недопустимое значение пульса")

    @staticmethod
    def validate_pulse(bpm: int) -> None:
        if not 30 <= bpm <= 250:
            raise ValueError("Недопустимое значение пульса")

    @staticmethod
    def validate_weight(weight: float) -> None:
        if not 2 <= weight <= 500:
            raise ValueError("Недопустимое значение веса")


    @classmethod
    def prepare_bp_data(
        cls,
        *,
        user_id: int,
        systolic: int,
        diastolic: int,
        pulse: Optional[int] = None,
        session_id: Optional[UUID] = None,
        measured_at: Optional[datetime] = None,
    ) -> schemas.BPMeasurementCreate:
        cls.validate_bp(systolic, diastolic, pulse)
        normalized_measured_at = cls.normalize_measured_at(measured_at)
        return schemas.BPMeasurementCreate(
            user_id=user_id,
            systolic=systolic,
            diastolic=diastolic,
            pulse=pulse,
            session_id=session_id,
            measured_at=normalized_measured_at,
        )

    @classmethod
    def prepare_pulse_data(
        cls,
        *,
        user_id: int,
        bpm: int,
        session_id: Optional[UUID] = None,
        measured_at: Optional[datetime] = None,
    ) -> schemas.PulseMeasurementCreate:
        cls.validate_pulse(bpm)
        normalized_measured_at = cls.normalize_measured_at(measured_at)
        return schemas.PulseMeasurementCreate(
            user_id=user_id,
            bpm=bpm,
            session_id=session_id,
            measured_at=normalized_measured_at,
        )

    @classmethod
    def prepare_weight_data(
        cls,
        *,
        user_id: int,
        weight: float,
        session_id: Optional[UUID] = None,
        measured_at: Optional[datetime] = None,
    ) -> schemas.WeightMeasurementCreate:
        cls.validate_weight(weight)
        normalized_measured_at = cls.normalize_measured_at(measured_at)
        return schemas.WeightMeasurementCreate(
            user_id=user_id,
            weight=weight,
            session_id=session_id,
            measured_at=normalized_measured_at,
        )

    @staticmethod
    def parse_bp_text(text: str) -> tuple[int, int]:
        cleaned = text.replace(",", ".").strip()
        if "/" in cleaned:
            parts = cleaned.split("/")
        else:
            parts = cleaned.split()
        if len(parts) < 2:
            raise ValueError("Введите давление в формате 120/80")
        systolic = int(float(parts[0]))
        diastolic = int(float(parts[1]))
        return systolic, diastolic

    @staticmethod
    def parse_float(text: str) -> float:
        return float(text.replace(",", ".").strip())

    @staticmethod
    def parse_int(text: str) -> int:
        return int(float(text.strip()))
