from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _is_active(entry: dict[str, object], *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if str(entry.get("status") or "active") != "active":
        return False
    expires_at = _parse_dt(entry.get("expires_at"))
    if expires_at is None:
        return True
    return expires_at > current


def merge_st_memory(
    existing: list[dict[str, object]] | None,
    updates: list[dict[str, object]] | None,
    *,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    current = now or datetime.now(UTC)
    by_key: dict[str, dict[str, object]] = {}

    for item in existing or []:
        if not _is_active(item, now=current):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        by_key[key] = dict(item)

    for item in updates or []:
        if not _is_active(item, now=current):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        by_key[key] = dict(item)

    return list(by_key.values())


class InMemorySTMemoryStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._store: dict[tuple[int, str, str], list[dict[str, object]]] = {}

    def read(self, *, patient_id: int, session_id: str, thread_id: str) -> list[dict[str, object]]:
        key = (patient_id, session_id, thread_id)
        with self._lock:
            current = merge_st_memory(self._store.get(key, []), [])
            self._store[key] = current
            return [dict(item) for item in current]

    def write(
        self,
        *,
        patient_id: int,
        session_id: str,
        thread_id: str,
        updates: list[dict[str, object]] | None,
    ) -> list[dict[str, object]]:
        key = (patient_id, session_id, thread_id)
        with self._lock:
            current = self._store.get(key, [])
            merged = merge_st_memory(current, updates or [])
            self._store[key] = merged
            return [dict(item) for item in merged]

    def clear(self, *, patient_id: int, session_id: str, thread_id: str) -> None:
        key = (patient_id, session_id, thread_id)
        with self._lock:
            self._store.pop(key, None)

    def clear_all(self) -> None:
        with self._lock:
            self._store.clear()


st_memory_store = InMemorySTMemoryStore()
