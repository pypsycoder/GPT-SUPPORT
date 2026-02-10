# ============================================
# Sleep Tracker Service: TIB, SE, late_entry, dialysis_day
# ============================================
# Расчёт TIB (переход через полночь), валидация SE (Q2b <= TIB), late_entry после 14:00.

from __future__ import annotations

import datetime
from typing import Optional

from app.sleep_tracker import schemas


def _parse_time(s: str) -> tuple[int, int]:
    """'HH:MM' -> (hours, minutes)."""
    parts = s.strip().split(":")
    if len(parts) != 2:
        raise ValueError("Формат времени: HH:MM")
    return int(parts[0]), int(parts[1])


def compute_tib_minutes(sleep_onset: str, wake_time: str) -> int:
    """
    TIB в минутах. Учитывает переход через полночь (sleep_onset > wake_time по часам).
    """
    h1, m1 = _parse_time(sleep_onset)
    h2, m2 = _parse_time(wake_time)
    start_m = h1 * 60 + m1
    end_m = h2 * 60 + m2
    if end_m <= start_m:
        end_m += 24 * 60
    return end_m - start_m


def validate_tib_soft(tib_minutes: int) -> Optional[str]:
    """
    Мягкое предупреждение: TIB < 2 ч или > 14 ч.
    Возвращает сообщение или None.
    """
    if tib_minutes < 2 * 60:
        return "Проверьте время, кажется что-то не так (слишком короткий сон)."
    if tib_minutes > 14 * 60:
        return "Проверьте время, кажется что-то не так (слишком длинный сон)."
    return None


def tst_hours_to_minutes(tst_hours: float) -> int:
    """Часы (0–12, шаг 0.5) в минуты."""
    return int(round(tst_hours * 60))


def compute_sleep_efficiency_pct(tst_minutes: int, tib_minutes: int) -> float:
    """SE = TST / TIB * 100. Округляем до 1 знака."""
    if tib_minutes <= 0:
        return 0.0
    return round(100.0 * tst_minutes / tib_minutes, 1)


def validate_se_hard(tst_minutes: int, tib_minutes: int) -> None:
    """
    Hard validation: Q2b (TST) не может быть больше TIB.
    SE > 100% невозможно — выбросить ошибку.
    """
    if tst_minutes > tib_minutes:
        raise ValueError(
            "Время фактического сна не может быть больше времени в кровати. "
            "Проверьте время отхода ко сну, пробуждения и количество часов сна."
        )


def is_late_entry(submitted_at: datetime.datetime) -> bool:
    """Запись после 14:00 по локальному времени считаем поздней."""
    # Используем local time: 14:00
    if submitted_at.tzinfo:
        local = submitted_at.astimezone()
    else:
        local = submitted_at
    return local.hour >= 14


def compute_retrospective_days(submitted_at: datetime.datetime, sleep_date: datetime.date) -> int:
    """retrospective_days = submitted_at.date − sleep_date в днях. Для утреннего ввода = 1."""
    sub_date = submitted_at.date() if submitted_at.tzinfo else submitted_at.replace(tzinfo=datetime.timezone.utc).date()
    return (sub_date - sleep_date).days


class SleepTrackerService:
    """Подготовка данных записи сна перед сохранением."""

    @classmethod
    def prepare_record(
        cls,
        *,
        patient_id: int,
        payload: schemas.SleepRecordCreate,
        submitted_at: datetime.datetime,
        dialysis_day: Optional[bool],
    ) -> dict:
        """
        Вычисляет tib_minutes, tst_minutes, sleep_efficiency_pct, retrospective_days;
        проверяет SE (TST <= TIB); формирует late_entry.
        Возвращает dict для создания SleepRecord в БД.
        """
        tib_minutes = compute_tib_minutes(payload.sleep_onset, payload.wake_time)
        tst_minutes = tst_hours_to_minutes(payload.tst_hours)
        validate_se_hard(tst_minutes, tib_minutes)
        se_pct = compute_sleep_efficiency_pct(tst_minutes, tib_minutes)
        retrospective_days = compute_retrospective_days(submitted_at, payload.sleep_date)

        disturbances = payload.sleep_disturbances
        if disturbances and "none" in disturbances:
            disturbances = ["none"]

        return {
            "patient_id": patient_id,
            "sleep_date": payload.sleep_date,
            "submitted_at": submitted_at,
            "late_entry": is_late_entry(submitted_at),
            "dialysis_day": dialysis_day,
            "retrospective_days": retrospective_days,
            "edit_count": 0,
            "sleep_onset": payload.sleep_onset,
            "wake_time": payload.wake_time,
            "tib_minutes": tib_minutes,
            "tst_minutes": tst_minutes,
            "sleep_efficiency_pct": se_pct,
            "night_awakenings": payload.night_awakenings,
            "sleep_latency": payload.sleep_latency,
            "morning_wellbeing": payload.morning_wellbeing,
            "daytime_nap": payload.daytime_nap,
            "sleep_disturbances": disturbances,
        }

    @classmethod
    def prepare_update(
        cls,
        payload: schemas.SleepRecordUpdate,
    ) -> dict:
        """Подготовка данных для UPDATE: те же расчёты, без sleep_date/submitted_at/edit_count."""
        tib_minutes = compute_tib_minutes(payload.sleep_onset, payload.wake_time)
        tst_minutes = tst_hours_to_minutes(payload.tst_hours)
        validate_se_hard(tst_minutes, tib_minutes)
        se_pct = compute_sleep_efficiency_pct(tst_minutes, tib_minutes)
        disturbances = payload.sleep_disturbances
        if disturbances and "none" in disturbances:
            disturbances = ["none"]
        return {
            "sleep_onset": payload.sleep_onset,
            "wake_time": payload.wake_time,
            "tib_minutes": tib_minutes,
            "tst_minutes": tst_minutes,
            "sleep_efficiency_pct": se_pct,
            "night_awakenings": payload.night_awakenings,
            "sleep_latency": payload.sleep_latency,
            "morning_wellbeing": payload.morning_wellbeing,
            "daytime_nap": payload.daytime_nap,
            "sleep_disturbances": disturbances,
        }
