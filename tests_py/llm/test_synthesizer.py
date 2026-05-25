"""Tests for supervisor response synthesis."""

from app.llm.supervisor.synthesizer import ResponseSynthesizer


def test_synthesizer_orders_blocks_and_deduplicates():
    response = ResponseSynthesizer().synthesize(
        [
            {"kind": "action", "text": "Сделай один шаг.", "dedupe_key": "step"},
            {"kind": "validation", "text": "Похоже, сейчас тебе непросто.", "dedupe_key": "support"},
            {"kind": "explanation", "text": "Это понятная реакция на нагрузку.", "dedupe_key": "why"},
            {"kind": "action", "text": "Сделай один шаг.", "dedupe_key": "step"},
        ]
    )

    assert response == "Похоже, сейчас тебе непросто. Это понятная реакция на нагрузку. Сделай один шаг."
