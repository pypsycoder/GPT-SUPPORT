from __future__ import annotations

import pytest

from app.llm.memory import (
    MemoryCandidate,
    MemoryScope,
    MemoryWriterContext,
    WriteDecision,
    build_lt_entry,
    build_st_entry,
    decide_memory_write,
)


pytestmark = [pytest.mark.unit]


def test_decide_memory_write_writes_st_for_session_context() -> None:
    candidate = MemoryCandidate(
        candidate_id="cand_1",
        source_layer="clarifier",
        candidate_type="current_intent",
        key="current_intent",
        value="practical_day_support",
        patient_id=1,
        session_id="sess_1",
        thread_id="thread_1",
        memory_scope=MemoryScope.ST,
        evidence=["user wants help getting through the day"],
    )

    decision = decide_memory_write(candidate)

    assert decision.decision == WriteDecision.WRITE
    assert decision.target_memory == "st"
    assert decision.reason == "session_context_needed"
    assert decision.ttl_seconds is not None


def test_decide_memory_write_rejects_specialist_direct_write() -> None:
    candidate = MemoryCandidate(
        candidate_id="cand_2",
        source_layer="psych_support",
        candidate_type="current_problem",
        key="current_problem",
        value="anxiety_before_dialysis",
        patient_id=1,
    )

    decision = decide_memory_write(candidate)

    assert decision.decision == WriteDecision.REJECT
    assert decision.reason == "forbidden_direct_writer"


def test_decide_memory_write_promotes_explicit_preference_to_lt() -> None:
    candidate = MemoryCandidate(
        candidate_id="cand_3",
        source_layer="clarifier",
        candidate_type="explicit_user_preference",
        key="response_style_preference",
        value="short_practical_answers",
        patient_id=1,
        policy_hint="explicit_user_preference",
        evidence=["user said: keep it short and practical"],
    )

    decision = decide_memory_write(candidate)

    assert decision.decision == WriteDecision.WRITE
    assert decision.target_memory == "lt"
    assert decision.reason == "explicit_user_preference_accepted"


def test_decide_memory_write_promotes_repeated_pattern_to_lt_when_threshold_met() -> None:
    candidate = MemoryCandidate(
        candidate_id="cand_4",
        source_layer="system",
        candidate_type="repeated_behavior_signal",
        key="content_preference",
        value="practice_first",
        patient_id=1,
        policy_hint="repeated_pattern",
        evidence_count=2,
    )

    decision = decide_memory_write(candidate)

    assert decision.decision == WriteDecision.WRITE
    assert decision.target_memory == "lt"
    assert decision.reason == "repeated_pattern_confirmed"


def test_decide_memory_write_rejects_lt_candidate_without_enough_evidence() -> None:
    candidate = MemoryCandidate(
        candidate_id="cand_5",
        source_layer="system",
        candidate_type="repeated_behavior_signal",
        key="content_preference",
        value="practice_first",
        patient_id=1,
        memory_scope=MemoryScope.LT,
        policy_hint="stable_behavior_signal",
        evidence_count=1,
    )

    decision = decide_memory_write(candidate)

    assert decision.decision == WriteDecision.REJECT
    assert decision.reason == "lt_policy_not_satisfied"


def test_decide_memory_write_uses_context_counts_for_stable_behavior() -> None:
    candidate = MemoryCandidate(
        candidate_id="cand_6",
        source_layer="system",
        candidate_type="repeated_behavior_signal",
        key="support_mode_preference",
        value="routine_first",
        patient_id=1,
        policy_hint="stable_behavior_signal",
        evidence_count=1,
    )
    context = MemoryWriterContext(
        repeated_counts={("support_mode_preference", "routine_first"): 3},
    )

    decision = decide_memory_write(candidate, context=context)

    assert decision.decision == WriteDecision.WRITE
    assert decision.target_memory == "lt"
    assert decision.reason == "stable_behavior_confirmed"


def test_build_st_entry_requires_session_and_thread() -> None:
    candidate = MemoryCandidate(
        candidate_id="cand_7",
        source_layer="clarifier",
        candidate_type="current_problem",
        key="current_problem",
        value="low_energy_today",
        patient_id=1,
        session_id="sess_7",
        thread_id="thread_7",
        memory_scope=MemoryScope.ST,
    )
    decision = decide_memory_write(candidate)

    entry = build_st_entry(candidate, decision, memory_id="st_1")

    assert entry.key == "current_problem"
    assert entry.session_id == "sess_7"
    assert entry.thread_id == "thread_7"
    assert entry.status == "active"
    assert entry.expires_at


def test_build_lt_entry_uses_policy_hint_as_source_policy() -> None:
    candidate = MemoryCandidate(
        candidate_id="cand_8",
        source_layer="progress",
        candidate_type="progress_event",
        key="stable_progress_fact",
        value="lesson_sleep_passed",
        patient_id=1,
        policy_hint="progress_event",
        evidence=["lesson sleep passed"],
    )
    decision = decide_memory_write(candidate)

    entry = build_lt_entry(candidate, decision, memory_id="lt_1")

    assert entry.key == "stable_progress_fact"
    assert entry.source_policy == "progress_event"
    assert entry.evidence_count == 1
    assert entry.status == "active"
