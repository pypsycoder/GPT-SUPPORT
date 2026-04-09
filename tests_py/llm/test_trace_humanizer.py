"""Tests for human-readable supervisor trace."""

from app.llm.trace_humanizer import build_human_trace


def test_human_trace_marks_generic_distress_context_clarification():
    trace = build_human_trace(
        {
            "supervisor": {
                "enabled": True,
                "message_type": "short_answer",
                "selected_agents": [],
                "used_pending_answer": True,
                "needs_clarification": True,
                "response_mode": "hybrid_clarify",
                "context_sufficiency": {
                    "support": False,
                    "plan": False,
                },
                "goal_analysis": {
                    "used": True,
                    "goal": None,
                    "goal_status": "generic_distress",
                    "clarification_reason": "generic_distress",
                    "attempts_total": 2,
                    "succeeded_on_attempt": 2,
                    "final_status": "success",
                },
                "state_after": {
                    "clarification_streak": 2,
                },
                "turn_diagnostics": {
                    "clarification_gate": {
                        "reason": "generic_distress",
                    }
                },
                "llm_draft": {
                    "enabled": True,
                    "used": True,
                },
            }
        }
    )

    supervisor_section = next(section for section in trace if section["title"] == "Supervisor")
    assert "LLM goal analysis: success on attempt 2." in supervisor_section["items"]
    assert "LLM goal extraction reason: generic_distress." in supervisor_section["items"]
    assert "Clarification reason: generic_distress." in supervisor_section["items"]
    assert "Response mode: hybrid_clarify." in supervisor_section["items"]
    assert "LLM decided context is insufficient for support and insufficient for plan." in supervisor_section["items"]
    assert "Clarification streak: 2/5." in supervisor_section["items"]
    assert "LLM распознала generic distress -> context clarification." in supervisor_section["items"]


def test_human_trace_marks_failed_goal_analysis_after_retries():
    trace = build_human_trace(
        {
            "supervisor": {
                "enabled": True,
                "goal_analysis": {
                    "used": True,
                    "attempts_total": 3,
                    "succeeded_on_attempt": None,
                    "final_status": "failed_after_retries",
                },
            }
        }
    )

    supervisor_section = next(section for section in trace if section["title"] == "Supervisor")
    assert "LLM goal analysis failed after 3 attempts." in supervisor_section["items"]
