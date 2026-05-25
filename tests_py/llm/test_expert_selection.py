"""Tests for agent selection rules."""

from app.llm.supervisor import CurrentState
from app.llm.supervisor.experts import select_agents


def test_select_agents_prefers_support_then_plan():
    state = CurrentState(intent="plan", signals=["distress", "needs_plan"])

    assert select_agents(state) == ["emotional_support", "planning"]


def test_select_agents_picks_education_for_inform():
    state = CurrentState(intent="inform", signals=["needs_explanation"])

    assert select_agents(state) == ["education"]


def test_select_agents_is_limited_to_two():
    state = CurrentState(intent="plan", signals=["distress", "needs_plan", "needs_explanation"])

    assert select_agents(state) == ["emotional_support", "planning"]
