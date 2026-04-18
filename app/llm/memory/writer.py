from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.llm.memory.models import (
    LTMemoryEntry,
    MemoryCandidate,
    MemoryScope,
    MemoryWriteDecision,
    STMemoryEntry,
    WriteDecision,
)

DEFAULT_ST_TTL_SECONDS = 2 * 60 * 60

FORBIDDEN_DIRECT_WRITERS = {
    "psych_support",
    "routine",
    "education",
    "composer",
    "critic",
}

ST_ONLY_CANDIDATE_TYPES = {
    "current_problem",
    "current_intent",
    "context_fact",
    "active_flow",
    "active_help_mode",
    "clarifier_state",
    "session_constraint",
}

LT_ALLOWED_POLICIES = {
    "explicit_user_preference",
    "repeated_pattern",
    "progress_event",
    "stable_behavior_signal",
}

LT_IMMEDIATE_POLICIES = {
    "explicit_user_preference",
    "progress_event",
}

REPEATED_PATTERN_MIN_EVIDENCE = 2
STABLE_BEHAVIOR_MIN_EVIDENCE = 3


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _utc_after(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


@dataclass(slots=True)
class MemoryWriterContext:
    existing_lt_keys: set[str] = field(default_factory=set)
    repeated_counts: dict[tuple[str, str], int] = field(default_factory=dict)
    st_ttl_seconds: int = DEFAULT_ST_TTL_SECONDS


def decide_memory_write(
    candidate: MemoryCandidate,
    *,
    context: MemoryWriterContext | None = None,
) -> MemoryWriteDecision:
    ctx = context or MemoryWriterContext()

    if candidate.source_layer in FORBIDDEN_DIRECT_WRITERS:
        return MemoryWriteDecision(
            candidate_id=candidate.candidate_id,
            decision=WriteDecision.REJECT,
            target_memory="none",
            reason="forbidden_direct_writer",
        )

    if candidate.policy_hint and candidate.policy_hint not in LT_ALLOWED_POLICIES:
        return MemoryWriteDecision(
            candidate_id=candidate.candidate_id,
            decision=WriteDecision.REJECT,
            target_memory="none",
            reason="unknown_policy_hint",
        )

    if candidate.policy_hint in LT_IMMEDIATE_POLICIES:
        return MemoryWriteDecision(
            candidate_id=candidate.candidate_id,
            decision=WriteDecision.WRITE,
            target_memory=MemoryScope.LT.value,
            reason=f"{candidate.policy_hint}_accepted",
            ttl_seconds=None,
            merge_strategy="replace_by_key",
            review_needed=False,
        )

    if candidate.policy_hint == "repeated_pattern":
        evidence_count = max(
            candidate.evidence_count,
            ctx.repeated_counts.get((candidate.key, str(candidate.value)), 0),
        )
        if evidence_count >= REPEATED_PATTERN_MIN_EVIDENCE:
            return MemoryWriteDecision(
                candidate_id=candidate.candidate_id,
                decision=WriteDecision.WRITE,
                target_memory=MemoryScope.LT.value,
                reason="repeated_pattern_confirmed",
                ttl_seconds=None,
                merge_strategy="increment_evidence",
                review_needed=False,
            )

    if candidate.policy_hint == "stable_behavior_signal":
        evidence_count = max(
            candidate.evidence_count,
            ctx.repeated_counts.get((candidate.key, str(candidate.value)), 0),
        )
        if evidence_count >= STABLE_BEHAVIOR_MIN_EVIDENCE:
            return MemoryWriteDecision(
                candidate_id=candidate.candidate_id,
                decision=WriteDecision.WRITE,
                target_memory=MemoryScope.LT.value,
                reason="stable_behavior_confirmed",
                ttl_seconds=None,
                merge_strategy="replace_by_key",
                review_needed=False,
            )

    if candidate.candidate_type in ST_ONLY_CANDIDATE_TYPES or candidate.memory_scope == MemoryScope.ST:
        return MemoryWriteDecision(
            candidate_id=candidate.candidate_id,
            decision=WriteDecision.WRITE,
            target_memory=MemoryScope.ST.value,
            reason="session_context_needed",
            ttl_seconds=ctx.st_ttl_seconds,
            merge_strategy="replace_by_key",
            review_needed=False,
        )

    if candidate.memory_scope == MemoryScope.LT:
        return MemoryWriteDecision(
            candidate_id=candidate.candidate_id,
            decision=WriteDecision.REJECT,
            target_memory="none",
            reason="lt_policy_not_satisfied",
        )

    return MemoryWriteDecision(
        candidate_id=candidate.candidate_id,
        decision=WriteDecision.REJECT,
        target_memory="none",
        reason="no_write_policy_matched",
    )


def build_st_entry(
    candidate: MemoryCandidate,
    decision: MemoryWriteDecision,
    *,
    memory_id: str,
) -> STMemoryEntry:
    if decision.target_memory != MemoryScope.ST.value:
        raise ValueError("Decision target_memory is not st")
    if not candidate.session_id or not candidate.thread_id:
        raise ValueError("ST-memory requires session_id and thread_id")

    created_at = candidate.created_at or _utc_now()
    return STMemoryEntry(
        memory_id=memory_id,
        patient_id=candidate.patient_id,
        session_id=candidate.session_id,
        thread_id=candidate.thread_id,
        key=candidate.key,
        value=candidate.value,
        source_layer=candidate.source_layer,
        evidence=list(candidate.evidence),
        created_at=created_at,
        updated_at=created_at,
        expires_at=_utc_after(decision.ttl_seconds or DEFAULT_ST_TTL_SECONDS),
        status="active",
    )


def build_lt_entry(
    candidate: MemoryCandidate,
    decision: MemoryWriteDecision,
    *,
    memory_id: str,
) -> LTMemoryEntry:
    if decision.target_memory != MemoryScope.LT.value:
        raise ValueError("Decision target_memory is not lt")

    created_at = candidate.created_at or _utc_now()
    return LTMemoryEntry(
        memory_id=memory_id,
        patient_id=candidate.patient_id,
        key=candidate.key,
        value=candidate.value,
        source_policy=candidate.policy_hint or decision.reason,
        evidence_count=max(candidate.evidence_count, len(candidate.evidence) or 1),
        evidence_examples=list(candidate.evidence[:3]),
        created_at=created_at,
        updated_at=created_at,
        status="active",
    )
