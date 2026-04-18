"""Async runner for Graph v2 supervisor module."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.llm.langgraph_supervisor.builder import build_langgraph
from app.llm.langgraph_supervisor.models import FirstModuleInput, FirstModuleState
from app.llm.langgraph_supervisor.nodes import (
    delegation_analyze_node,
    delegation_validate_node,
    finalize_reply_node,
    intake_analyze_node,
    intake_execute_node,
    intake_validate_node,
    invoke_emotional_expert_node,
)

NodeFn = Callable[[FirstModuleState], Awaitable[FirstModuleState] | FirstModuleState]

GRAPH_ORDER: tuple[tuple[str, NodeFn], ...] = (
    ("intake_analyze", intake_analyze_node),
    ("intake_validate", intake_validate_node),
    ("intake_execute", intake_execute_node),
    ("delegation_analyze", delegation_analyze_node),
    ("delegation_validate", delegation_validate_node),
    ("invoke_emotional_expert", invoke_emotional_expert_node),
    ("finalize_reply", finalize_reply_node),
)

_COMPILED_GRAPH = None


async def _run_sequential(payload: FirstModuleInput) -> FirstModuleState:
    state = FirstModuleState.from_input(payload)
    for _node_name, node_fn in GRAPH_ORDER:
        result = node_fn(state)
        state = await result if hasattr(result, "__await__") else result
    return state


async def run_first_module(payload: FirstModuleInput) -> FirstModuleState:
    global _COMPILED_GRAPH

    if _COMPILED_GRAPH is None:
        try:
            _COMPILED_GRAPH = build_langgraph()
        except RuntimeError:
            _COMPILED_GRAPH = False

    if _COMPILED_GRAPH is False:
        return await _run_sequential(payload)

    graph_state = await _COMPILED_GRAPH.ainvoke(FirstModuleState.from_input(payload).to_graph_dict())
    return FirstModuleState.from_graph_dict(graph_state)
