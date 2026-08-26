"""Tests for stateful supervisor models."""

import json

from app.llm.supervisor import CurrentState, ExpertResult, ExpertTask, PendingQuestion, SupervisorTurnResult


def test_current_state_roundtrip_is_json_compatible():
    state = CurrentState(
        domain="health",
        intent="support",
        goal="получить поддержку",
        slots={"distress_level": 7},
        risk_flags=["before_dialysis"],
        signals=["distress"],
        facts=["mentioned_dialysis"],
        pending_question=PendingQuestion(
            slot_name="distress_level",
            question_text="Насколько тяжело сейчас по шкале от 0 до 10?",
            expected_kind="scale_0_10",
            attempts=1,
            reason="distress_scale",
        ),
        last_selected_agents=["emotional_support"],
        needs_clarification=True,
        clarification_streak=2,
        last_clarification_reason="generic_distress",
        last_goal_status="resolved",
    )

    payload = state.to_dict()
    dumped = json.dumps(payload, ensure_ascii=False)

    assert "before_dialysis" in dumped
    assert '"clarification_streak": 2' in dumped
    assert CurrentState.from_dict(payload).to_dict() == payload


def test_expert_models_roundtrip():
    task = ExpertTask(
        agent_name="planning",
        goal="получить следующий шаг",
        domain="daily_routine",
        intent="plan",
        state_snapshot={"domain": "daily_routine"},
    )
    result = ExpertResult(
        agent_name="planning",
        content_blocks=[{"kind": "action", "text": "Сделай один шаг.", "dedupe_key": "step"}],
        state_delta={"signals_add": ["plan_provided"]},
        confidence=0.9,
    )
    turn = SupervisorTurnResult(
        reply="Сделай один шаг.",
        state_delta={"goal_set": "получить следующий шаг"},
        updated_state=CurrentState(goal="получить следующий шаг"),
        message_type="full_message",
        selected_agents=["planning"],
        used_pending_answer=False,
        needs_clarification=False,
        diagnostics={"selected_agents": ["planning"]},
    )

    assert ExpertTask.from_dict(task.to_dict()).to_dict() == task.to_dict()
    assert ExpertResult.from_dict(result.to_dict()).to_dict() == result.to_dict()
    assert SupervisorTurnResult.from_dict(turn.to_dict()).to_dict() == turn.to_dict()
