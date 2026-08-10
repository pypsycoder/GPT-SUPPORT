"""Одноагентная ветка (шаг 4): один структурный вызов вместо цепочки узлов.

Живёт параллельно со старой веткой, включается ``LLM_SINGLE_AGENT=1``.
Интент SAFETY на неё не переводится — кризис остаётся на старом пути.
"""

from app.llm.agent.loop import Agent, AgentRun, build_layers
from app.llm.agent.schemas import AgentReply
from app.llm.agent.techniques import TechniqueState, advance as advance_technique

__all__ = [
    "Agent",
    "AgentRun",
    "AgentReply",
    "TechniqueState",
    "advance_technique",
    "build_layers",
    "single_agent_enabled",
]

import os

ENV_FLAG = "LLM_SINGLE_AGENT"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def single_agent_enabled() -> bool:
    """Включена ли одноагентная ветка (флаг окружения)."""
    return str(os.getenv(ENV_FLAG, "")).strip().lower() in _TRUTHY
