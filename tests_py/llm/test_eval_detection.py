from __future__ import annotations

from scripts.run_llm_eval import EvalCase, _detect_issues


def test_detect_issues_does_not_flag_food_advice_inside_word_fragments():
    case = EvalCase(
        case_id="sleep_anxiety_mixed",
        category="mixed",
        text="Последние дни плохо сплю и тревожусь перед диализом, что можно сделать?",
        expected_policy="sleep_support",
        forbid_checks=["food_advice"],
        require_checks=[],
        notes="",
    )

    diagnostics = {"prompt": {"selected_policy": "sleep_support"}}
    response = (
        "Попробуй следующие шаги:\n"
        "- Используй методы релаксации перед отдыхом.\n"
        "- Ограничь использование гаджетов за час до сна, предпочти чтение книги или спокойную музыку.\n"
    )

    issues = _detect_issues(response, diagnostics, case)

    assert "food_advice" not in issues


def test_detect_issues_recognizes_action_step_stems():
    case = EvalCase(
        case_id="sleep_bad_night",
        category="sleep",
        text="Я почти не спал этой ночью и теперь весь день разбит. Что можно сделать сегодня?",
        expected_policy="sleep_support",
        forbid_checks=[],
        require_checks=[],
        notes="",
    )

    diagnostics = {"prompt": {"selected_policy": "sleep_support"}}
    response = "Создайте небольшой вечерний ритуал и уберите гаджеты за час до сна."

    issues = _detect_issues(response, diagnostics, case)

    assert "no_action_step" not in issues
