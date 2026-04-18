from app.llm.trace_humanizer import build_human_trace


def test_human_trace_shows_graph_v2_blocks():
    trace = build_human_trace(
        {
            "supervisor": {
                "enabled": True,
                "message_type": "full_message",
                "graph_path": [
                    "intake_analyze",
                    "intake_validate",
                    "intake_execute",
                    "delegation_analyze",
                    "delegation_validate",
                    "invoke_emotional_expert",
                    "finalize_reply",
                ],
                "selected_agents": ["emotional_support"],
                "intake": {
                    "card": {
                        "problem": "страх перед диализом",
                        "needs_clarification": "нет",
                        "ready_to_delegate": "да",
                    },
                    "llm": {
                        "succeeded_on_attempt": 1,
                    },
                },
                "delegation": {
                    "card": {
                        "expert": "эмоциональная_поддержка",
                        "task": "помочь справиться со страхом перед процедурой",
                    },
                    "llm": {
                        "succeeded_on_attempt": 1,
                    },
                },
                "expert": {
                    "card": {
                        "step_now": "Скажи, что именно пугает сильнее всего.",
                    },
                    "llm": {
                        "succeeded_on_attempt": 1,
                    },
                },
            }
        }
    )

    supervisor_section = next(section for section in trace if section["title"] == "Supervisor")
    assert "Supervisor определил тип хода: full_message." in supervisor_section["items"]
    assert "Graph path: intake_analyze -> intake_validate -> intake_execute -> delegation_analyze -> delegation_validate -> invoke_emotional_expert -> finalize_reply." in supervisor_section["items"]
    assert "Проблема: страх перед диализом." in supervisor_section["items"]
    assert "Нужно уточнение: нет." in supervisor_section["items"]
    assert "Эксперт: эмоциональная_поддержка." in supervisor_section["items"]
    assert "Шаг сейчас: Скажи, что именно пугает сильнее всего.." in supervisor_section["items"]


def test_human_trace_marks_failed_intake_analysis_after_retries():
    trace = build_human_trace(
        {
            "supervisor": {
                "enabled": True,
                "intake": {
                    "llm": {
                        "attempts_total": 3,
                        "final_status": "failed_after_retries",
                    }
                },
            }
        }
    )

    supervisor_section = next(section for section in trace if section["title"] == "Supervisor")
    assert "Intake analysis failed after 3 attempts." in supervisor_section["items"]


def test_human_trace_includes_retry_details_for_supervisor_steps():
    trace = build_human_trace(
        {
            "supervisor": {
                "enabled": True,
                "intake": {
                    "llm": {
                        "attempts_total": 3,
                        "succeeded_on_attempt": 2,
                        "final_status": "success",
                        "failures": [
                            {
                                "attempt": 1,
                                "error_type": "ValueError",
                                "error_message": "missing required fields",
                                "raw_excerpt": "Проблема: тревога",
                            }
                        ],
                    }
                },
            }
        }
    )

    supervisor_section = next(section for section in trace if section["title"] == "Supervisor")
    assert "Intake analysis: success on attempt 2." in supervisor_section["items"]
    assert "Intake analysis: retries before success = 1." in supervisor_section["items"]
    assert any("Intake analysis retry #1: ValueError - missing required fields | raw: Проблема: тревога." == item for item in supervisor_section["items"])
