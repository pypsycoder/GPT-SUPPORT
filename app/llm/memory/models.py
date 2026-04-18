from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class MemoryScope(StrEnum):
    ST = "st"
    LT = "lt"
    UNDECIDED = "undecided"


class WriteDecision(StrEnum):
    WRITE = "write"
    REJECT = "reject"
    DEFER = "defer"


@dataclass(slots=True)
class MemoryCandidate:
    candidate_id: str
    source_layer: str
    candidate_type: str
    key: str
    value: object
    patient_id: int
    session_id: str | None = None
    thread_id: str | None = None
    memory_scope: MemoryScope = MemoryScope.UNDECIDED
    evidence: list[str] = field(default_factory=list)
    confidence: float | None = None
    created_at: str = ""
    policy_hint: str = ""
    evidence_count: int = 1
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class MemoryWriteDecision:
    candidate_id: str
    decision: WriteDecision
    target_memory: str = "none"
    reason: str = ""
    ttl_seconds: int | None = None
    merge_strategy: str = "replace_by_key"
    review_needed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class STMemoryEntry:
    memory_id: str
    patient_id: int
    session_id: str
    thread_id: str
    key: str
    value: object
    source_layer: str
    evidence: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    expires_at: str = ""
    status: str = "active"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class LTMemoryEntry:
    memory_id: str
    patient_id: int
    key: str
    value: object
    source_policy: str
    evidence_count: int = 1
    evidence_examples: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    status: str = "active"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
