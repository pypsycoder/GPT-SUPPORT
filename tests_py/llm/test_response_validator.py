from __future__ import annotations

import pytest

from app.llm.response_validator import validate_response_for_rewrite


pytestmark = [pytest.mark.unit]


def test_validate_response_for_rewrite_detects_food_and_template_patterns():
    result = validate_response_for_rewrite(
        "Попробуй легкий перекус и травяной чай. Ты справишься!"
    )

    assert result.triggered is True
    assert result.reasons == ["food_advice", "template_reassurance"]


def test_validate_response_for_rewrite_detects_generic_food_drink_language():
    result = validate_response_for_rewrite(
        "Можно поесть что-то легкое или выпить чай, а потом немного отдохнуть."
    )

    assert result.triggered is True
    assert result.reasons == ["food_advice"]


def test_validate_response_for_rewrite_detects_early_escalation():
    result = validate_response_for_rewrite(
        "Поговори с врачом или медсестрой. Потом попробуй сделать несколько вдохов."
    )

    assert result.triggered is True
    assert result.reasons == ["early_escalation"]


def test_validate_response_for_rewrite_detects_infinitive_doctor_escalation():
    result = validate_response_for_rewrite(
        "Если не станет легче, лучше обратиться к врачу для консультации."
    )

    assert result.triggered is True
    assert result.reasons == ["early_escalation", "no_action_step"]


def test_validate_response_for_rewrite_allows_soft_escalation_at_end():
    result = validate_response_for_rewrite(
        "Сделай короткую паузу.\n- Немного замедлись.\n- Подыши спокойно.\n- Если это повторится, обсуди это на следующем диализе."
    )

    assert result.triggered is False
    assert result.reasons == []


def test_validate_response_for_rewrite_detects_care_team_assumption():
    result = validate_response_for_rewrite(
        "Поговори с медсестрой, они точно помогут и подскажут, что делать."
    )

    assert result.triggered is True
    assert result.reasons == ["early_escalation", "care_team_assumption"]


def test_validate_response_for_rewrite_allows_clean_support_response():
    result = validate_response_for_rewrite(
        "Сделай короткую паузу, немного замедлись и попробуй несколько спокойных вдохов."
    )

    assert result.triggered is False
    assert result.reasons == []


def test_validate_response_for_rewrite_does_not_match_food_inside_other_words():
    result = validate_response_for_rewrite(
        "Ограничь использование гаджетов перед сном, предпочти чтение книги или спокойную музыку."
    )

    assert result.triggered is False
    assert result.reasons == []


def test_validate_response_for_rewrite_detects_missing_action_step():
    result = validate_response_for_rewrite(
        "Похоже, тебе сейчас правда тяжело. Если хочешь, можем вместе разобраться, что беспокоит сильнее всего."
    )

    assert result.triggered is True
    assert result.reasons == ["no_action_step"]


def test_validate_response_for_rewrite_recognizes_action_stems_like_sozdaite_i_uberite():
    result = validate_response_for_rewrite(
        "Создайте небольшой вечерний ритуал и уберите гаджеты за час до сна."
    )

    assert result.triggered is False
    assert result.reasons == []


def test_validate_response_for_rewrite_allows_validation_only_when_explicitly_enabled():
    result = validate_response_for_rewrite(
        "Тебе тревожно, и ты плохо спал. Это может сказываться на самочувствии.",
        allow_validation_only=True,
    )

    assert result.triggered is False
    assert result.reasons == []
