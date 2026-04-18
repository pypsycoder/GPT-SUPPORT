"""Optional LangGraph builder for Graph v2."""

from __future__ import annotations

from app.llm.langgraph_supervisor.models import FirstModuleState
from app.llm.langgraph_supervisor.nodes import (
    delegation_analyze_node,
    delegation_validate_node,
    finalize_reply_node,
    intake_analyze_node,
    intake_execute_node,
    intake_validate_node,
    invoke_emotional_expert_node,
)

try:  # pragma: no cover - optional dependency
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover - optional dependency
    END = None
    StateGraph = None


def build_langgraph():
    if StateGraph is None or END is None:
        raise RuntimeError("langgraph is not installed in the current environment")

    graph = StateGraph(dict)

    def wrap(node_fn):
        async def _wrapped(payload: dict) -> dict:
            state = FirstModuleState.from_graph_dict(payload)
            updated = node_fn(state)
            if hasattr(updated, "__await__"):
                updated = await updated
            return updated.to_graph_dict()

        return _wrapped

    graph.add_node("intake_analyze", wrap(intake_analyze_node))
    graph.add_node("intake_validate", wrap(intake_validate_node))
    graph.add_node("intake_execute", wrap(intake_execute_node))
    graph.add_node("delegation_analyze", wrap(delegation_analyze_node))
    graph.add_node("delegation_validate", wrap(delegation_validate_node))
    graph.add_node("invoke_emotional_expert", wrap(invoke_emotional_expert_node))
    graph.add_node("finalize_reply", wrap(finalize_reply_node))

    graph.set_entry_point("intake_analyze")
    graph.add_edge("intake_analyze", "intake_validate")
    graph.add_edge("intake_validate", "intake_execute")
    graph.add_edge("intake_execute", "delegation_analyze")
    graph.add_edge("delegation_analyze", "delegation_validate")
    graph.add_edge("delegation_validate", "invoke_emotional_expert")
    graph.add_edge("invoke_emotional_expert", "finalize_reply")
    graph.add_edge("finalize_reply", END)
    return graph.compile()
