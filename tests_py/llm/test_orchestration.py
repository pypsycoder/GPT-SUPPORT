from __future__ import annotations

import json

import pytest

from app.llm.orchestration import (
    _agent_rag_context,
    _call_json_step,
    _extract_json_object,
    _postprocess_route_with_context,
    _specialist_context_snapshot,
    analyze_rag_grounding,
    run_full_llm_orchestration,
    run_specialist_grounding_probe,
    RouteDecision,
    SpecialistOutput,
)
from app.llm.router import ModelTier, RequestType, RouterResult


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


async def test_extract_json_object_accepts_yaml_like_llm_output():
    payload = _extract_json_object(
        """
        {
          selected_agents: [routine, psych_support]
          primary_agent: routine
          secondary_agents: [psych_support]
        }
        """
    )

    assert payload["primary_agent"] == "routine"
    assert payload["selected_agents"] == ["routine", "psych_support"]


async def test_call_json_step_repairs_non_json_reply():
    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        async def call(self, messages, system_prompt):
            self.calls += 1
            if self.calls == 1:
                return ("Нужны routine и psych_support, главный routine.", 10, 5, 20)
            return (
                json.dumps(
                    {
                        "selected_agents": ["routine", "psych_support"],
                        "primary_agent": "routine",
                        "secondary_agents": ["psych_support"],
                        "routing_reasons": ["sleep_context"],
                        "risk_flags": [],
                        "why_not_selected": {"education": ["not_needed"]},
                    },
                    ensure_ascii=False,
                ),
                12,
                7,
                25,
            )

    payload, trace, tokens_in, tokens_out, latency_ms = await _call_json_step(
        client=FakeClient(),
        system_prompt="ROUTER",
        user_content="CTX",
        stage="router",
        agent_name="router",
        input_summary="плохо спал и тревожусь",
        selected_context_sections=["patient_summary_prompt"],
    )

    assert payload["primary_agent"] == "routine"
    assert trace.raw_output["json_repaired"] is True
    assert "routine" in trace.raw_output["original_raw_text"]
    assert tokens_in == 22
    assert tokens_out == 12
    assert latency_ms == 45


async def test_psych_support_context_uses_only_practice_metadata():
    context_text, sections = _specialist_context_snapshot(
        agent_name="psych_support",
        user_input="Мне тревожно и я хочу справиться с тревогой.",
        router_result=RouterResult(
            request_type=RequestType.EMOTIONAL,
            model_tier=ModelTier.PRO,
            domain_hint="emotion",
            priority=2,
        ),
        parser_mood="bad",
        parser_domain_hints=["emotion"],
        patient_summary_prompt=["Есть признаки тревоги."],
        rag_context=["Урок про сон и тревогу", "Фрагмент про плохой сон"],
        rag_grounding_items=[
            {
                "rag_index": 0,
                "lesson_code": "sleep_intro",
                "practice": {"id": 7, "title": "Дыхательная практика"},
                "cta": {"cta_type": "practice", "cta_reason": "lesson_mastered"},
            }
        ],
    )

    assert sections == ["patient_summary_prompt", "practice_metadata"]
    assert "RAG CTA metadata:" in context_text
    assert "practice_title=Дыхательная практика" in context_text
    assert "Урок про сон и тревогу" not in context_text
    assert "Фрагмент про плохой сон" not in context_text


async def test_routine_context_uses_role_specific_rag_view():
    context_text, sections = _specialist_context_snapshot(
        agent_name="routine",
        user_input="РџРѕСЃР»Рµ РїР»РѕС…РѕР№ РЅРѕС‡Рё СЏ СЂР°Р·Р±РёС‚.",
        router_result=RouterResult(
            request_type=RequestType.SIMPLE,
            model_tier=ModelTier.PRO,
            domain_hint="sleep",
            priority=1,
        ),
        parser_mood="bad",
        parser_domain_hints=["sleep"],
        patient_summary_prompt=["Р’ РїРѕСЃР»РµРґРЅРёРµ РґРЅРё СЃРѕРЅ СѓС…СѓРґС€РёР»СЃСЏ."],
        rag_context=["РЈСЂРѕРє РїСЂРѕ СЃРѕРЅ СЃ lesson framing"],
        rag_views={
            "routine": ["РЎРґРµР»Р°Р№ РєРѕСЂРѕС‚РєСѓСЋ РїР°СѓР·Сѓ Рё СЃРЅРёР·СЊ С‚РµРјРї РЅР° Р±Р»РёР¶Р°Р№С€РёРµ С‡Р°СЃС‹."],
            "education": ["РЈСЂРѕРє В«РЎРѕРЅВ». Р РµР»РµРІР°РЅС‚РЅС‹Р№ С„СЂР°РіРјРµРЅС‚: ..."],
        },
        rag_grounding_items=[
            {
                "rag_index": 0,
                "lesson_code": "sleep_intro",
                "cta": {"cta_type": "lesson", "cta_reason": "lesson_unread"},
            }
        ],
    )

    assert sections == ["patient_summary_prompt", "rag_view_routine"]
    assert "РЎРґРµР»Р°Р№ РєРѕСЂРѕС‚РєСѓСЋ РїР°СѓР·Сѓ Рё СЃРЅРёР·СЊ С‚РµРјРї РЅР° Р±Р»РёР¶Р°Р№С€РёРµ С‡Р°СЃС‹." in context_text
    assert "РЈСЂРѕРє РїСЂРѕ СЃРѕРЅ СЃ lesson framing" not in context_text
    assert "RAG CTA metadata" in context_text
    assert "lesson_unread" not in context_text


async def test_routine_context_does_not_fallback_to_general_rag():
    context_text, sections = _specialist_context_snapshot(
        agent_name="routine",
        user_input="Мне тревожно и я плохо спал.",
        router_result=RouterResult(
            request_type=RequestType.EMOTIONAL,
            model_tier=ModelTier.PRO,
            domain_hint="sleep",
            priority=2,
        ),
        parser_mood="bad",
        parser_domain_hints=["sleep", "emotion"],
        patient_summary_prompt=["Сон ухудшился на фоне тревоги."],
        rag_context=["Урок «Сон». Попробуйте дыхание и прочитайте материал полностью."],
        rag_views={"routine": [], "education": ["Урок «Сон». ..."]},
        rag_grounding_items=[],
    )

    assert sections == ["patient_summary_prompt", "rag_view_routine"]
    assert "Урок «Сон»" not in context_text
    assert "прочитайте материал полностью" not in context_text


async def test_agent_rag_context_keeps_global_fallback_only_for_education():
    rag_context = ["Общий lesson-shaped chunk"]
    rag_views = {"psych_support": [], "routine": [], "education": []}

    assert _agent_rag_context(agent_name="routine", rag_context=rag_context, rag_views=rag_views) == []
    assert _agent_rag_context(agent_name="psych_support", rag_context=rag_context, rag_views=rag_views) == []
    assert _agent_rag_context(agent_name="education", rag_context=rag_context, rag_views=rag_views) == rag_context


async def test_postprocess_route_skips_routine_when_no_routine_rag_view():
    route = _postprocess_route_with_context(
        route=RouteDecision(
            selected_agents=["psych_support", "routine"],
            primary_agent="routine",
            secondary_agents=["psych_support"],
            routing_reasons=["sleep_context", "emotion_signal"],
            risk_flags=[],
            why_not_selected={"education": ["not_needed"]},
        ),
        rag_context=["Урок «Сон». Релевантный фрагмент: ..."],
        rag_views={"psych_support": [], "routine": [], "education": ["Урок «Сон». ..."]},
    )

    assert route.selected_agents == ["psych_support"]
    assert route.primary_agent == "psych_support"
    assert route.secondary_agents == []
    assert "no_routine_rag_view" in route.why_not_selected["routine"]
    assert "routine_skipped_no_actionable_rag" in route.routing_reasons


async def test_analyze_rag_grounding_marks_used_and_ignored_chunks():
    output = SpecialistOutput(
        agent="routine",
        status="ok",
        signals=["сон"],
        recommended_actions=["снизить темп на ближайшие часы"],
        avoid=[],
        draft="Сделай короткую паузу и снизь темп на ближайшие часы.",
        notes_for_composer=[],
        selected_context_sections=["patient_summary_prompt", "rag_context"],
    )

    grounding = analyze_rag_grounding(
        output=output,
        rag_context=[
            "Если после плохой ночи сил мало, можно снизить темп на ближайшие часы и сделать короткую паузу.",
            "Сон связан с тревогой и внутренним напряжением.",
        ],
    )

    assert grounding["grounding_status"] == "used_rag"
    assert grounding["used_rag_indices"] == [0]
    assert grounding["ignored_rag_indices"] == [1]


async def test_run_specialist_grounding_probe_collects_rag_grounding():
    class FakeClient:
        def __init__(self) -> None:
            self._responses = iter(
                [
                    (
                        json.dumps(
                            {
                                "agent": "psych_support",
                                "status": "ok",
                                "signals": ["тревога"],
                                "recommended_actions": [],
                                "avoid": ["шаблонное утешение"],
                                "draft": "Похоже, сейчас тебе правда тяжело.",
                                "cta_type": "none",
                                "cta_label": "",
                                "cta_reason": "no_cta",
                                "cta_target": {},
                                "cta_soft_text": "",
                                "notes_for_composer": ["мягкий тон"],
                                "selected_context_sections": ["patient_summary_prompt", "practice_metadata"],
                            },
                            ensure_ascii=False,
                        ),
                        40,
                        14,
                        80,
                    ),
                    (
                        json.dumps(
                            {
                                "agent": "education",
                                "status": "ok",
                                "signals": ["объяснение"],
                                "recommended_actions": ["материал про сон"],
                                "avoid": ["длинная теория"],
                                "draft": "Иногда после плохой ночи помогает снизить темп на ближайшие часы.",
                                "cta_type": "lesson",
                                "cta_label": "Сон",
                                "cta_reason": "lesson_unread",
                                "cta_target": {"lesson_code": "sleep_intro"},
                                "cta_soft_text": "Если хочешь, потом можно посмотреть короткий урок про сон.",
                                "notes_for_composer": ["кратко"],
                                "selected_context_sections": ["patient_summary_prompt", "rag_context"],
                            },
                            ensure_ascii=False,
                        ),
                        42,
                        16,
                        85,
                    ),
                    (
                        json.dumps(
                            {
                                "agent": "routine",
                                "status": "ok",
                                "signals": ["сон"],
                                "recommended_actions": ["сделать короткую паузу", "снизить темп на ближайшие часы"],
                                "avoid": ["еда"],
                                "draft": "Сделай короткую паузу и снизь темп на ближайшие часы.",
                                "cta_type": "practice",
                                "cta_label": "Дыхательная практика",
                                "cta_reason": "lesson_mastered",
                                "cta_target": {"practice_id": 7, "lesson_code": "sleep_intro"},
                                "cta_soft_text": "Если это уже знакомо, можно потом попробовать дыхательную практику.",
                                "notes_for_composer": ["практические шаги"],
                                "selected_context_sections": ["patient_summary_prompt", "rag_context"],
                            },
                            ensure_ascii=False,
                        ),
                        44,
                        18,
                        90,
                    ),
                ]
            )

        async def call(self, messages, system_prompt):
            return next(self._responses)

    result = await run_specialist_grounding_probe(
        client=FakeClient(),
        user_input="Из-за тревоги почти не спал(а), сейчас совсем тяжело.",
        router_result=RouterResult(
            request_type=RequestType.EMOTIONAL,
            model_tier=ModelTier.PRO,
            domain_hint="sleep",
            priority=1,
        ),
        parser_mood="bad",
        parser_domain_hints=["sleep", "emotion"],
        patient_summary_prompt=["В последние дни сон ухудшился.", "Есть признаки тревоги."],
        rag_context=["Если после плохой ночи сил мало, можно снизить темп на ближайшие часы и сделать короткую паузу."],
        rag_views={
            "psych_support": ["Практика по теме: Дыхательная практика. Связанный материал: Сон"],
            "routine": ["Если после плохой ночи сил мало, можно снизить темп на ближайшие часы и сделать короткую паузу."],
            "education": ["Урок «Сон». Релевантный фрагмент: Если после плохой ночи сил мало, можно снизить темп на ближайшие часы и сделать короткую паузу."],
        },
        rag_grounding_items=[
            {
                "rag_index": 0,
                "lesson_code": "sleep_intro",
                "cta": {
                    "cta_type": "practice",
                    "cta_reason": "lesson_mastered",
                    "cta_target": {"practice_id": 7, "lesson_code": "sleep_intro"},
                },
                "practice": {"id": 7, "title": "Дыхательная практика"},
            }
        ],
    )

    assert [item.agent for item in result.specialists] == ["psych_support", "education", "routine"]
    assert result.tokens_input == 126
    assert result.tokens_output == 48
    assert len(result.trace) == 3
    assert all(trace.stage == "specialist_probe" for trace in result.trace)
    assert result.trace[1].normalized_output["rag_grounding"]["used_rag_indices"] == [0]
    assert result.trace[2].normalized_output["rag_grounding"]["used_rag_indices"] == [0]
    assert result.trace[1].normalized_output["cta_diagnostics"]["cta_type"] == "lesson"
    assert result.trace[2].normalized_output["cta_diagnostics"]["cta_type"] == "practice"


async def test_run_full_llm_orchestration_returns_structured_result(monkeypatch):
    monkeypatch.setattr("app.llm.orchestration.load_orchestration_prompt", lambda filename: f"PROMPT::{filename}")

    class FakeClient:
        def __init__(self) -> None:
            self._responses = iter(
                [
                    (
                        json.dumps(
                            {
                                "selected_agents": ["routine", "psych_support"],
                                "primary_agent": "routine",
                                "secondary_agents": ["psych_support"],
                                "routing_reasons": ["sleep_context"],
                                "risk_flags": [],
                                "why_not_selected": {"education": ["not_needed"]},
                            },
                            ensure_ascii=False,
                        ),
                        50,
                        10,
                        80,
                    ),
                    (
                        json.dumps(
                            {
                                "agent": "routine",
                                "status": "ok",
                                "signals": ["sleep"],
                                "recommended_actions": ["pause"],
                                "avoid": ["food_advice"],
                                "draft": "Сделай короткую паузу.",
                                "notes_for_composer": ["short_horizon"],
                                "selected_context_sections": ["patient_summary_prompt", "rag_context"],
                            },
                            ensure_ascii=False,
                        ),
                        40,
                        10,
                        70,
                    ),
                    (
                        json.dumps(
                            {
                                "agent": "psych_support",
                                "status": "ok",
                                "signals": ["stress"],
                                "recommended_actions": ["gentle_pace"],
                                "avoid": ["template_reassurance"],
                                "draft": "Не дави на себя слишком сильно.",
                                "notes_for_composer": ["soft_tone"],
                                "selected_context_sections": ["patient_summary_prompt", "practice_metadata"],
                            },
                            ensure_ascii=False,
                        ),
                        42,
                        12,
                        72,
                    ),
                    (
                        json.dumps(
                            {
                                "status": "ok",
                                "draft_response": "Сделай короткую паузу и не дави на себя слишком сильно.",
                                "blocks": ["routine", "psych_support"],
                                "composition_rules": ["one_answer"],
                                "guidance_text": "Собран один ответ.",
                            },
                            ensure_ascii=False,
                        ),
                        45,
                        12,
                        75,
                    ),
                    (
                        json.dumps(
                            {
                                "status": "pass",
                                "violations": [],
                                "severity": "low",
                                "rewrite_required": False,
                                "rewrite_reasons": [],
                                "route_feedback": [],
                                "critic_notes": ["ok"],
                            },
                            ensure_ascii=False,
                        ),
                        30,
                        8,
                        60,
                    ),
                ]
            )

        async def call(self, messages, system_prompt):
            return next(self._responses)

    result = await run_full_llm_orchestration(
        client=FakeClient(),
        user_input="Плохо спал и устал.",
        router_result=RouterResult(
            request_type=RequestType.SIMPLE,
            model_tier=ModelTier.PRO,
            domain_hint="sleep",
            priority=1,
        ),
        parser_mood="bad",
        parser_domain_hints=["sleep", "emotion"],
        patient_summary_prompt=["Сон ухудшился."],
        rag_context=["Если после плохой ночи сил мало, можно снизить темп на ближайшие часы."],
    )

    assert result.final_response == "Сделай короткую паузу и не дави на себя слишком сильно."
    assert result.route.primary_agent == "routine"
    assert [item.agent for item in result.specialists] == ["routine", "psych_support"]
    assert result.composer.draft_response
    assert result.critic.status == "pass"
    assert result.rewrite["final_response_source"] == "composer"
    assert len(result.trace) == 5


async def test_run_full_llm_orchestration_skips_routine_when_routine_view_empty(monkeypatch):
    monkeypatch.setattr("app.llm.orchestration.load_orchestration_prompt", lambda filename: f"PROMPT::{filename}")

    class FakeClient:
        def __init__(self) -> None:
            self._responses = iter(
                [
                    (
                        json.dumps(
                            {
                                "selected_agents": ["psych_support", "routine"],
                                "primary_agent": "routine",
                                "secondary_agents": ["psych_support"],
                                "routing_reasons": ["sleep_context", "emotion_signal"],
                                "risk_flags": [],
                                "why_not_selected": {"education": ["not_needed"]},
                            },
                            ensure_ascii=False,
                        ),
                        50,
                        10,
                        80,
                    ),
                    (
                        json.dumps(
                            {
                                "agent": "psych_support",
                                "status": "ok",
                                "signals": ["тревога", "плохой сон"],
                                "recommended_actions": [],
                                "avoid": ["шаблонное утешение", "ранняя эскалация"],
                                "draft": "Тебе тревожно, и ты плохо спал. Это может быть непросто.",
                                "notes_for_composer": ["поддержи мягко и без советов"],
                                "selected_context_sections": ["patient_summary_prompt", "practice_metadata"],
                            },
                            ensure_ascii=False,
                        ),
                        42,
                        12,
                        72,
                    ),
                    (
                        json.dumps(
                            {
                                "status": "ok",
                                "draft_response": "Тебе тревожно, и ты плохо спал. Это может быть непросто.",
                                "blocks": ["acknowledgement"],
                                "composition_rules": ["one_answer"],
                                "guidance_text": "Оставлен только validation-only вклад.",
                            },
                            ensure_ascii=False,
                        ),
                        45,
                        12,
                        75,
                    ),
                    (
                        json.dumps(
                            {
                                "status": "pass",
                                "violations": [],
                                "severity": "low",
                                "rewrite_required": False,
                                "rewrite_reasons": [],
                                "route_feedback": [],
                                "critic_notes": ["ok"],
                            },
                            ensure_ascii=False,
                        ),
                        30,
                        8,
                        60,
                    ),
                ]
            )

        async def call(self, messages, system_prompt):
            return next(self._responses)

    result = await run_full_llm_orchestration(
        client=FakeClient(),
        user_input="мне тревожно и я плохо спал",
        router_result=RouterResult(
            request_type=RequestType.EMOTIONAL,
            model_tier=ModelTier.PRO,
            domain_hint="sleep",
            priority=2,
        ),
        parser_mood="bad",
        parser_domain_hints=["sleep", "emotion"],
        patient_summary_prompt=["Сон ухудшился.", "Есть признаки тревоги."],
        rag_context=["Урок «Сон». Релевантный фрагмент: ..."],
        rag_views={"psych_support": [], "routine": [], "education": ["Урок «Сон». ..."]},
        rag_grounding_items=[],
    )

    assert result.route.selected_agents == ["psych_support"]
    assert result.route.primary_agent == "psych_support"
    assert [item.agent for item in result.specialists] == ["psych_support"]
    assert result.final_response == "Тебе тревожно, и ты плохо спал. Это может быть непросто."


async def test_run_full_llm_orchestration_strips_ungrounded_composer_actions(monkeypatch):
    monkeypatch.setattr("app.llm.orchestration.load_orchestration_prompt", lambda filename: f"PROMPT::{filename}")

    class FakeClient:
        def __init__(self) -> None:
            self._responses = iter(
                [
                    (
                        json.dumps(
                            {
                                "selected_agents": ["psych_support"],
                                "primary_agent": "psych_support",
                                "secondary_agents": [],
                                "routing_reasons": ["emotion_signal"],
                                "risk_flags": [],
                                "why_not_selected": {"routine": ["no_routine_rag_view"]},
                            },
                            ensure_ascii=False,
                        ),
                        50,
                        10,
                        80,
                    ),
                    (
                        json.dumps(
                            {
                                "agent": "psych_support",
                                "status": "ok",
                                "signals": ["тревога", "плохой сон"],
                                "recommended_actions": [],
                                "avoid": ["шаблонное утешение", "ранняя эскалация", "выдуманные техники"],
                                "draft": "Тебе тревожно, и ты плохо спал. Это может быть непросто.",
                                "notes_for_composer": ["признай состояние", "не выдумывать советы"],
                                "selected_context_sections": ["patient_summary_prompt", "practice_metadata"],
                            },
                            ensure_ascii=False,
                        ),
                        42,
                        12,
                        72,
                    ),
                    (
                        json.dumps(
                            {
                                "status": "ok",
                                "draft_response": "Ты говоришь, что тебе тревожно и было сложно спать. Попробуй создать спокойную обстановку, избегай экранов, подыши глубже и обратись к психологу.",
                                "blocks": ["acknowledgement", "actions", "soft_escalation"],
                                "composition_rules": ["one_answer"],
                                "guidance_text": "Собран ответ с рекомендациями.",
                            },
                            ensure_ascii=False,
                        ),
                        45,
                        12,
                        75,
                    ),
                    (
                        json.dumps(
                            {
                                "status": "pass",
                                "violations": [],
                                "severity": "low",
                                "rewrite_required": False,
                                "rewrite_reasons": [],
                                "route_feedback": [],
                                "critic_notes": ["ok"],
                            },
                            ensure_ascii=False,
                        ),
                        30,
                        8,
                        60,
                    ),
                ]
            )

        async def call(self, messages, system_prompt):
            return next(self._responses)

    result = await run_full_llm_orchestration(
        client=FakeClient(),
        user_input="мне тревожно и плохо спал",
        router_result=RouterResult(
            request_type=RequestType.EMOTIONAL,
            model_tier=ModelTier.PRO,
            domain_hint="sleep",
            priority=2,
        ),
        parser_mood="bad",
        parser_domain_hints=["sleep", "emotion"],
        patient_summary_prompt=["Сон ухудшился.", "Есть признаки тревоги."],
        rag_context=["Урок «Сон». Релевантный фрагмент: ..."],
        rag_views={"psych_support": [], "routine": [], "education": ["Урок «Сон». ..."]},
        rag_grounding_items=[],
    )

    assert result.final_response == "Тебе тревожно, и ты плохо спал. Это может быть непросто."
    assert result.composer.blocks == ["acknowledgement"]
    assert result.composer.composition_rules == ["validation_only", "no_ungrounded_actions"]
    assert result.composer.guidance_text == "Composer fallback: removed ungrounded actions and kept validation-only response."
