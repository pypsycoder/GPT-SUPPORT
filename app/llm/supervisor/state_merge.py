"""Incremental state merge helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.llm.supervisor.models import CurrentState


# merge_state_delta
def merge_state_delta(current_state: CurrentState, delta: dict[str, Any] | None) -> CurrentState:
    payload = current_state.to_dict()

    for key, value in dict(delta or {}).items():
        if key.endswith("_add"):
            target_key = key[:-4]
            existing = list(payload.get(target_key) or [])
            for item in list(value or []):
                if item not in existing:
                    existing.append(item)
            payload[target_key] = existing
            continue

        if key.endswith("_set"):
            payload[key[:-4]] = deepcopy(value)
            continue

        if value is None:
            continue
        payload[key] = deepcopy(value)

    return CurrentState.from_dict(payload)
