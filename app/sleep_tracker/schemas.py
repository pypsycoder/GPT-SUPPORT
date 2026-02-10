# ============================================
# Sleep Tracker Schemas: Pydantic и enums
# ============================================
# Маппинг на PSQI/ICF, значения полей по ТЗ.

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


# --- Enums (значения полей) ---

class NightAwakenings(str):
    NONE = "none"
    ONE_TWO = "1-2"
    THREE_PLUS = "3+"


class SleepLatency(str):
    FAST = "fast"           # До 15 минут
    MID = "15-30"           # 15–30 минут
    LONG = "30+"            # Больше 30 минут


class MorningWellbeing(str):
    RESTED = "rested"
    SLIGHTLY_TIRED = "slightly_tired"
    VERY_TIRED = "very_tired"


class DaytimeNap(str):
    NONE = "none"
    UNDER_1H = "under_1h"
    OVER_1H = "over_1h"


class SleepDisturbance(str):
    PAIN = "pain"
    ITCH = "itch"
    NOCTURIA = "nocturia"
    RLS = "rls"
    ANXIETY = "anxiety"
    NOISE = "noise"
    NONE = "none"


# Строковые значения для API (Literal/str)
NIGHT_AWAKENINGS_VALUES = ("none", "1-2", "3+")
SLEEP_LATENCY_VALUES = ("fast", "15-30", "30+")
MORNING_WELLBEING_VALUES = ("rested", "slightly_tired", "very_tired")
DAYTIME_NAP_VALUES = ("none", "under_1h", "over_1h")
SLEEP_DISTURBANCE_VALUES = ("pain", "itch", "nocturia", "rls", "anxiety", "noise", "none")


# --- API schemas ---

class SleepRecordCreate(BaseModel):
    """Тело запроса для создания записи сна (от пациента)."""
    sleep_date: date                    # дата ночи (YYYY-MM-DD), выбирается на экране выбора ночи
    sleep_onset: str                    # "HH:MM" (Q1)
    wake_time: str                      # "HH:MM" (Q2)
    tst_hours: float                    # Q2b, 0–12, шаг 0.5
    night_awakenings: str               # none | 1-2 | 3+
    sleep_latency: str                  # fast | 15-30 | 30+
    morning_wellbeing: str              # rested | slightly_tired | very_tired
    daytime_nap: Optional[str] = None   # none | under_1h | over_1h (Q6)
    sleep_disturbances: Optional[List[str]] = None  # Q7, может быть ["none"] или список причин

    @field_validator("sleep_onset")
    @classmethod
    def check_time_format(cls, v: str) -> str:
        if not v or ":" not in v:
            raise ValueError("Формат времени: HH:MM")
        parts = v.strip().split(":")
        if len(parts) != 2:
            raise ValueError("Формат времени: HH:MM")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Недопустимое время")
        return f"{h:02d}:{m:02d}"

    @field_validator("wake_time")
    @classmethod
    def check_wake_time(cls, v: str) -> str:
        if not v or ":" not in v:
            raise ValueError("Формат времени: HH:MM")
        parts = v.strip().split(":")
        if len(parts) != 2:
            raise ValueError("Формат времени: HH:MM")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Недопустимое время")
        return f"{h:02d}:{m:02d}"

    @field_validator("night_awakenings")
    @classmethod
    def check_night_awakenings(cls, v: str) -> str:
        if v not in NIGHT_AWAKENINGS_VALUES:
            raise ValueError("Допустимые значения: none, 1-2, 3+")
        return v

    @field_validator("sleep_latency")
    @classmethod
    def check_sleep_latency(cls, v: str) -> str:
        if v not in SLEEP_LATENCY_VALUES:
            raise ValueError("Допустимые значения: fast, 15-30, 30+")
        return v

    @field_validator("morning_wellbeing")
    @classmethod
    def check_morning_wellbeing(cls, v: str) -> str:
        if v not in MORNING_WELLBEING_VALUES:
            raise ValueError("Допустимые значения: rested, slightly_tired, very_tired")
        return v

    @field_validator("daytime_nap")
    @classmethod
    def check_daytime_nap(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in DAYTIME_NAP_VALUES:
            raise ValueError("Допустимые значения: none, under_1h, over_1h")
        return v

    @field_validator("sleep_disturbances")
    @classmethod
    def check_sleep_disturbances(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        for item in v:
            if item not in SLEEP_DISTURBANCE_VALUES:
                raise ValueError(f"Недопустимое значение: {item}")
        if "none" in v and len(v) > 1:
            return ["none"]
        return v


class SleepRecordRead(BaseModel):
    """Ответ API: одна запись сна."""
    model_config = ConfigDict(from_attributes=True)

    record_id: UUID
    patient_id: int
    sleep_date: date
    submitted_at: datetime
    updated_at: datetime
    late_entry: bool
    dialysis_day: Optional[bool]
    retrospective_days: Optional[int]
    edit_count: int
    sleep_onset: str
    wake_time: str
    tib_minutes: int
    tst_minutes: int
    sleep_efficiency_pct: float
    night_awakenings: str
    sleep_latency: str
    morning_wellbeing: str
    daytime_nap: Optional[str]
    sleep_disturbances: Optional[List[str]]


class SleepRecordUpdate(BaseModel):
    """Тело запроса для обновления записи сна (те же поля, что и create, без sleep_date)."""
    sleep_onset: str
    wake_time: str
    tst_hours: float
    night_awakenings: str
    sleep_latency: str
    morning_wellbeing: str
    daytime_nap: Optional[str] = None
    sleep_disturbances: Optional[List[str]] = None

    @field_validator("sleep_onset")
    @classmethod
    def check_time_format(cls, v: str) -> str:
        if not v or ":" not in v:
            raise ValueError("Формат времени: HH:MM")
        parts = v.strip().split(":")
        if len(parts) != 2:
            raise ValueError("Формат времени: HH:MM")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Недопустимое время")
        return f"{h:02d}:{m:02d}"

    @field_validator("wake_time")
    @classmethod
    def check_wake_time(cls, v: str) -> str:
        if not v or ":" not in v:
            raise ValueError("Формат времени: HH:MM")
        parts = v.strip().split(":")
        if len(parts) != 2:
            raise ValueError("Формат времени: HH:MM")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Недопустимое время")
        return f"{h:02d}:{m:02d}"

    @field_validator("night_awakenings")
    @classmethod
    def check_night_awakenings(cls, v: str) -> str:
        if v not in NIGHT_AWAKENINGS_VALUES:
            raise ValueError("Допустимые значения: none, 1-2, 3+")
        return v

    @field_validator("sleep_latency")
    @classmethod
    def check_sleep_latency(cls, v: str) -> str:
        if v not in SLEEP_LATENCY_VALUES:
            raise ValueError("Допустимые значения: fast, 15-30, 30+")
        return v

    @field_validator("morning_wellbeing")
    @classmethod
    def check_morning_wellbeing(cls, v: str) -> str:
        if v not in MORNING_WELLBEING_VALUES:
            raise ValueError("Допустимые значения: rested, slightly_tired, very_tired")
        return v

    @field_validator("daytime_nap")
    @classmethod
    def check_daytime_nap(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in DAYTIME_NAP_VALUES:
            raise ValueError("Допустимые значения: none, under_1h, over_1h")
        return v

    @field_validator("sleep_disturbances")
    @classmethod
    def check_sleep_disturbances(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        for item in v:
            if item not in SLEEP_DISTURBANCE_VALUES:
                raise ValueError(f"Недопустимое значение: {item}")
        if "none" in v and len(v) > 1:
            return ["none"]
        return v
