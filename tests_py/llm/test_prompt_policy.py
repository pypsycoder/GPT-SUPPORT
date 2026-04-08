from __future__ import annotations

import pytest

from app.llm.agent import load_prompt


pytestmark = [pytest.mark.unit]


def test_base_system_forbids_generic_hydration_advice():
    prompt = load_prompt("base_system.txt")

    assert "пить больше жидкости" in prompt
    assert "гемодиализ" in prompt


def test_sleep_prompt_forbids_generic_hydration_advice():
    prompt = load_prompt("domain_sleep.txt")

    assert "Не предлагай «пить больше жидкости»" in prompt


def test_sleep_prompt_forbids_food_and_drink_advice_without_request():
    prompt = load_prompt("domain_sleep.txt")

    assert "не давай советов про воду, напитки, чай, перекусы, еду" in prompt.lower()



def test_rewrite_prompt_mentions_forbidden_patterns():
    prompt = load_prompt("policy_response_rewrite.txt")

    assert "drink more water" in prompt.lower()
    assert "template reassurance" in prompt.lower()
    assert "do not replace one food or drink suggestion with another" in prompt.lower()
    assert "outside dialysis hours" in prompt.lower()
