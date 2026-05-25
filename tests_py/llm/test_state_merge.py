"""Tests for incremental state merge."""

from app.llm.supervisor import CurrentState, PendingQuestion, merge_state_delta


def test_merge_state_delta_overwrites_scalar_fields():
    state = CurrentState(domain="general", intent="support")

    merged = merge_state_delta(state, {"domain": "health", "goal": "получить поддержку"})

    assert merged.domain == "health"
    assert merged.goal == "получить поддержку"


def test_merge_state_delta_merges_add_lists_without_duplicates():
    state = CurrentState(signals=["distress"], risk_flags=["before_dialysis"])

    merged = merge_state_delta(
        state,
        {"signals_add": ["distress", "plan_provided"], "risk_flags_add": ["before_dialysis", "medical_risk"]},
    )

    assert merged.signals == ["distress", "plan_provided"]
    assert merged.risk_flags == ["before_dialysis", "medical_risk"]


def test_merge_state_delta_replaces_values_with_set_suffix():
    state = CurrentState(
        slots={"distress_level": 3},
        pending_question=PendingQuestion(
            slot_name="distress_level",
            question_text="?",
            expected_kind="scale_0_10",
        ),
    )

    merged = merge_state_delta(
        state,
        {"slots_set": {"distress_level": 8, "goal": "поддержка"}, "pending_question_set": None},
    )

    assert merged.slots == {"distress_level": 8, "goal": "поддержка"}
    assert merged.pending_question is None


def test_merge_state_delta_ignores_none_for_plain_scalar():
    state = CurrentState(goal="старое")

    merged = merge_state_delta(state, {"goal": None})

    assert merged.goal == "старое"
