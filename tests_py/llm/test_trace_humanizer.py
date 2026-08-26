from app.llm.trace_humanizer import build_human_trace


def test_human_trace_shows_agent_card_details():
    trace = build_human_trace(
        {
            "supervisor": {
                "enabled": True,
                "message_type": "full_message",
                "graph_path": ["agent"],
                "selected_agents": ["emotional_support"],
                "agent": {
                    "intent": "emotional_support",
                    "technique_id": "p01",
                    "safety_level": "none",
                    "safety_kind": "none",
                    "next_action": "предложить практику дыхания",
                },
            }
        }
    )

    supervisor_section = next(section for section in trace if section["title"] == "Supervisor")
    assert "Supervisor определил тип хода: full_message." in supervisor_section["items"]
    assert "Graph path: agent." in supervisor_section["items"]
    assert "Intent: emotional_support." in supervisor_section["items"]
    assert "Техника: p01." in supervisor_section["items"]
    assert "Следующее действие: предложить практику дыхания." in supervisor_section["items"]
    assert "Подключенные expert-агенты: emotional_support." in supervisor_section["items"]


def test_human_trace_shows_safety_level_when_not_none():
    items = _supervisor_items(
        {
            "enabled": True,
            "graph_path": ["agent"],
            "agent": {"intent": "safety", "safety_level": "concern", "safety_kind": "psychological"},
        }
    )

    assert "Safety: concern (psychological)." in items


def test_human_trace_hides_placeholder_technique_and_action():
    """Модель присылает 'нет', когда техники/действия не было — не показываем как факт."""
    items = _supervisor_items(
        {
            "enabled": True,
            "agent": {"intent": "smalltalk", "technique_id": "нет", "next_action": "нет", "safety_level": "none"},
        }
    )

    assert not any(item.startswith("Техника:") for item in items)
    assert not any(item.startswith("Следующее действие:") for item in items)


def test_human_trace_reports_agent_card_failure():
    items = _supervisor_items(
        {
            "enabled": True,
            "graph_path": ["agent"],
            "error": "schema validation failed twice",
        }
    )

    assert "Агент не отдал карточку: schema validation failed twice." in items


def test_human_trace_reports_disabled_supervisor():
    items = _supervisor_items({"enabled": False, "reason": "no_classification"})

    assert "Supervisor-path не использовался: no_classification." in items


def _supervisor_items(supervisor: dict) -> list[str]:
    trace = build_human_trace({"supervisor": supervisor})
    return next(section for section in trace if section["title"] == "Supervisor")["items"]
