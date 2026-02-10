# ============================================
# Dialysis CSV Import: парсинг и preview
# ============================================

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dialysis.models import Center, DialysisSchedule
from app.users.models import User

SHIFT_VALUES = frozenset({"morning", "afternoon", "evening"})
REQUIRED_HEADERS = ("patient_id", "center_name", "weekdays", "shift", "valid_from")


def _parse_weekdays(s: str) -> list[int] | None:
    if not s or not s.strip():
        return None
    parts = [p.strip() for p in s.split(";") if p.strip()]
    out = []
    for p in parts:
        try:
            n = int(p)
            if 1 <= n <= 7:
                out.append(n)
            else:
                return None
        except ValueError:
            return None
    return out if out else None


def _parse_date(s: str) -> date | None:
    if not s or not s.strip():
        return None
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        return None


async def parse_and_preview(
    session: AsyncSession,
    file_content: bytes | str,
) -> dict[str, Any]:
    """
    Парсит CSV и возвращает ready / conflicts / errors.
    file_content: содержимое файла (UTF-8).
    """
    if isinstance(file_content, bytes):
        text = file_content.decode("utf-8-sig")
    else:
        text = file_content
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return {"ready": [], "conflicts": [], "errors": [{"row_index": 0, "error_message": "Нет заголовков CSV"}]}
    missing = set(REQUIRED_HEADERS) - set(reader.fieldnames or [])
    if missing:
        return {
            "ready": [],
            "conflicts": [],
            "errors": [{"row_index": 0, "error_message": f"Отсутствуют колонки: {', '.join(sorted(missing))}"}],
        }
    ready = []
    conflicts = []
    errors = []
    for row_index, row in enumerate(reader, start=2):
        row_data = dict(row)
        patient_id_raw = (row.get("patient_id") or "").strip()
        if not patient_id_raw:
            errors.append({"row_index": row_index, "error_message": "Отсутствует patient_id"})
            continue
        try:
            patient_id = int(patient_id_raw)
        except ValueError:
            errors.append({"row_index": row_index, "error_message": f"Некорректный patient_id: {patient_id_raw!r}"})
            continue
        result = await session.execute(select(User).where(User.id == patient_id))
        user = result.scalar_one_or_none()
        if user is None:
            errors.append({"row_index": row_index, "error_message": f"Пациент не найден (id: {patient_id})"})
            continue
        center_name = (row.get("center_name") or "").strip()
        if not center_name:
            errors.append({"row_index": row_index, "error_message": "Отсутствует center_name"})
            continue
        result = await session.execute(select(Center).where(Center.name == center_name))
        center = result.scalar_one_or_none()
        if center is None:
            errors.append({"row_index": row_index, "error_message": f"Центр не найден по имени: {center_name!r}"})
            continue
        weekdays = _parse_weekdays(row.get("weekdays") or "")
        if weekdays is None:
            errors.append({"row_index": row_index, "error_message": "Некорректный формат weekdays (ожидается 1;3;5, числа 1–7)"})
            continue
        shift_raw = (row.get("shift") or "").strip().lower()
        if shift_raw not in SHIFT_VALUES:
            errors.append({"row_index": row_index, "error_message": f"Некорректная смена: {shift_raw!r}"})
            continue
        valid_from = _parse_date(row.get("valid_from") or "")
        if valid_from is None:
            errors.append({"row_index": row_index, "error_message": "Некорректная дата valid_from (ожидается YYYY-MM-DD)"})
            continue
        change_reason = (row.get("change_reason") or "").strip() or None
        parsed = {
            "patient_id": patient_id,
            "weekdays": weekdays,
            "shift": shift_raw,
            "valid_from": valid_from.isoformat(),
            "change_reason": change_reason,
        }
        result = await session.execute(
            select(DialysisSchedule)
            .where(DialysisSchedule.patient_id == patient_id)
            .where(DialysisSchedule.valid_to.is_(None))
        )
        active = result.scalar_one_or_none()
        if active is None:
            ready.append({"row_data": row_data, "parsed_schedule": parsed})
        else:
            existing_read = {
                "id": str(active.id),
                "patient_id": active.patient_id,
                "weekdays": list(active.weekdays) if active.weekdays else [],
                "shift": active.shift,
                "valid_from": active.valid_from.isoformat() if active.valid_from else None,
                "valid_to": active.valid_to.isoformat() if active.valid_to else None,
            }
            conflicts.append({
                "row_data": row_data,
                "existing_schedule": existing_read,
                "new_schedule": parsed,
            })
    return {"ready": ready, "conflicts": conflicts, "errors": errors}
