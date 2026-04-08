from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.llm import context_builder
from app.llm.errors import RetrievalError


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


async def test_build_context_bundle_collects_section_and_rag_diagnostics(monkeypatch):
    monkeypatch.setattr(
        context_builder,
        "_get_recent_vitals",
        AsyncMock(return_value=["BP 120/80"]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_medication_adherence",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_sleep_summary",
        AsyncMock(side_effect=RuntimeError("sleep source unavailable")),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_active_practices",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_last_scale_scores",
        AsyncMock(return_value=["HADS: 7"]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_recent_weight",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_recent_water",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_routine_summary",
        AsyncMock(return_value=["Routine: 4 of 7"]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_practices_summary",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_chat_history",
        AsyncMock(return_value=[{"role": "user", "content": "hi"}]),
    )
    monkeypatch.setattr(
        context_builder,
        "_get_rag_context",
        AsyncMock(
            return_value=(
                ["Relevant lesson chunk"],
                {
                    "backend": "python_cosine",
                    "backend_selected": "python_cosine",
                    "candidate_rows": 10,
                    "query_vector_dims": 1024,
                    "embedding_request_ms": 120,
                    "vector_search_ms": 45,
                    "progress_lookup_ms": 3,
                    "pgvector_extension_installed": False,
                    "pgvector_column_present": False,
                    "pgvector_index_present": False,
                    "pgvector_blocker": "pgvector_extension_missing",
                    "invalid_embedding_rows": 0,
                },
                [
                    {
                        "rag_index": 0,
                        "lesson_id": 10,
                        "lesson_code": "sleep_intro",
                        "lesson_title": "Сон",
                        "is_read": False,
                        "is_completed": False,
                        "has_passed_test": False,
                        "practice": None,
                        "cta": {
                            "cta_type": "lesson",
                            "cta_reason": "lesson_unread",
                            "cta_label": "Сон",
                            "cta_target": {"lesson_id": 10, "lesson_code": "sleep_intro"},
                        },
                    }
                ],
            )
        ),
    )

    bundle = await context_builder.build_context_bundle(
        patient_id=42,
        db=object(),
        query="long enough query for retrieval",
    )

    context = bundle["context"]
    diagnostics = bundle["diagnostics"]

    assert context["recent_vitals"] == ["BP 120/80"]
    assert context["sleep_summary"] == []
    assert context["rag_context"] == ["Relevant lesson chunk"]
    assert "patient_summary" in context
    assert "Повседневная рутина в последние дни давалась тяжело." in context["patient_summary"]
    assert "По последним шкалам есть признаки эмоционального напряжения." in context["patient_summary"]
    assert "По этой теме можно предложить пациенту подходящий обучающий материал." in context["patient_summary"]

    assert "recent_vitals" in diagnostics["sections_ok"]
    assert "sleep_summary" in diagnostics["sections_failed"]
    assert diagnostics["section_latency_ms"]["recent_vitals"] >= 0
    assert diagnostics["section_item_counts"]["recent_vitals"] == 1
    assert diagnostics["total_latency_ms"] >= 0
    assert diagnostics["summary_items"] == 3
    assert diagnostics["rag"]["attempted"] is True
    assert diagnostics["rag"]["hit_count"] == 1
    assert diagnostics["rag"]["error"] is None
    assert diagnostics["rag"]["backend"] == "python_cosine"
    assert diagnostics["rag"]["pgvector_blocker"] == "pgvector_extension_missing"
    assert diagnostics["rag"]["embedding_request_ms"] == 120
    assert diagnostics["rag"]["vector_search_ms"] == 45
    assert diagnostics["rag"]["progress_lookup_ms"] == 3
    assert context["rag_grounding_items"][0]["cta"]["cta_type"] == "lesson"
    assert diagnostics["rag"]["grounding_items"][0]["cta"]["cta_reason"] == "lesson_unread"


async def test_build_context_bundle_records_retrieval_error(monkeypatch):
    monkeypatch.setattr(context_builder, "_get_recent_vitals", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_medication_adherence", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_sleep_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_active_practices", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_last_scale_scores", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_recent_weight", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_recent_water", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_routine_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_practices_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_chat_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        context_builder,
        "_get_rag_context",
        AsyncMock(side_effect=RetrievalError("embedding provider unavailable")),
    )

    bundle = await context_builder.build_context_bundle(
        patient_id=42,
        db=object(),
        query="long enough query for retrieval",
    )

    diagnostics = bundle["diagnostics"]
    assert diagnostics["rag"]["attempted"] is True
    assert diagnostics["rag"]["hit_count"] == 0
    assert diagnostics["rag"]["error"] == "embedding provider unavailable"
    assert bundle["context"]["patient_summary"] == []


async def test_build_context_bundle_marks_short_query_rag_skip(monkeypatch):
    monkeypatch.setattr(context_builder, "_get_recent_vitals", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_medication_adherence", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_sleep_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_active_practices", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_last_scale_scores", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_recent_weight", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_recent_water", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_routine_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_practices_summary", AsyncMock(return_value=[]))
    monkeypatch.setattr(context_builder, "_get_chat_history", AsyncMock(return_value=[]))
    rag_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(context_builder, "_get_rag_context", rag_mock)

    bundle = await context_builder.build_context_bundle(
        patient_id=42,
        db=object(),
        query="short query",
    )

    diagnostics = bundle["diagnostics"]
    assert diagnostics["rag"]["attempted"] is False
    assert diagnostics["rag"]["skipped_reason"] == "query_too_short"
    rag_mock.assert_not_called()


async def test_get_rag_context_keeps_fragment_without_read_state(monkeypatch):
    monkeypatch.setattr(
        "app.rag.retriever.retrieve_relevant_modules_with_meta",
        AsyncMock(
            return_value={
                "modules": [
                    {
                        "lesson_id": 13,
                        "title": "Сон",
                        "chunk": "Если тревога мешает уснуть, начните с трёх медленных выдохов и снижайте темп перед сном.",
                    }
                ],
                "meta": {"backend": "pgvector"},
            }
        ),
    )
    monkeypatch.setattr(
        context_builder,
        "_build_rag_grounding_items",
        AsyncMock(
            return_value=[
                {
                    "rag_index": 0,
                    "lesson_id": 13,
                    "lesson_code": "sleep_lesson",
                    "lesson_title": "Сон",
                    "is_read": True,
                    "is_completed": True,
                    "has_passed_test": True,
                    "practice": {"id": 7, "title": "Дыхательная практика"},
                    "cta": {
                        "cta_type": "practice",
                        "cta_reason": "lesson_mastered",
                        "cta_label": "Дыхательная практика",
                        "cta_target": {"practice_id": 7, "lesson_id": 13, "lesson_code": "sleep_lesson"},
                    },
                }
            ]
        ),
    )

    lines, meta, grounding_items = await context_builder._get_rag_context(42, "Не могу уснуть", object())

    assert meta["backend"] == "pgvector"
    assert "Урок «Сон»." in lines[0]
    assert "трёх медленных выдохов" in lines[0]
    assert grounding_items[0]["cta"]["cta_type"] == "practice"
    assert grounding_items[0]["practice"]["title"] == "Дыхательная практика"


async def test_format_context_for_llm_prefers_patient_summary_over_raw_sections():
    context = {
        "patient_summary_prompt": [
            "В последние дни сон ухудшился.",
            "Приём лекарств в последнее время был неполным.",
        ],
        "patient_summary": [
            "В последние дни сон ухудшился.",
            "Приём лекарств в последнее время был неполным.",
            "Повседневная рутина в последние дни давалась тяжело.",
        ],
        "sleep_summary": ["Сон: среднее 5.2ч, тренд снижается"],
        "medication_adherence": ["Приём лекарств: 62% за 7 дней (9 из 14)"],
        "rag_context": ["По теме «Сон» есть урок — можешь предложить пациенту."],
    }

    text = context_builder.format_context_for_llm(context)

    assert "Краткая сводка за последние дни" in text
    assert "В последние дни сон ухудшился." in text
    assert "Приём лекарств в последнее время был неполным." in text
    assert "Сон: среднее 5.2ч, тренд снижается" not in text
    assert "Приём лекарств: 62% за 7 дней" not in text
    assert "Образовательные модули" in text


async def test_select_patient_summary_for_prompt_prefers_sleep_tags():
    context = {
        "patient_summary_items": [
            {"text": "В последние дни сон ухудшился.", "tags": ["sleep"], "priority": 100},
            {"text": "По последним шкалам есть признаки эмоционального напряжения.", "tags": ["emotion"], "priority": 85},
            {"text": "Контроль жидкости остаётся важной частью повседневной рутины.", "tags": ["water", "routine"], "priority": 50},
            {"text": "По этой теме можно предложить пациенту подходящий обучающий материал.", "tags": ["cta_lesson"], "priority": 30},
        ]
    }

    selected = context_builder.select_patient_summary_for_prompt(
        context,
        policy_name="sleep_support",
        parser_domain_hints=["sleep", "emotion"],
        effective_domain="sleep",
    )

    assert selected == [
        "В последние дни сон ухудшился.",
        "По последним шкалам есть признаки эмоционального напряжения.",
        "По этой теме можно предложить пациенту подходящий обучающий материал.",
    ]


async def test_select_patient_summary_for_prompt_prefers_routine_and_water_tags():
    context = {
        "patient_summary_items": [
            {"text": "Приём лекарств в последнее время был неполным.", "tags": ["medication", "routine"], "priority": 100},
            {"text": "Повседневная рутина в последние дни давалась тяжело.", "tags": ["routine"], "priority": 90},
            {"text": "Контроль жидкости остаётся важной частью повседневной рутины.", "tags": ["water", "routine"], "priority": 50},
            {"text": "По последним шкалам есть признаки эмоционального напряжения.", "tags": ["emotion"], "priority": 85},
        ]
    }

    selected = context_builder.select_patient_summary_for_prompt(
        context,
        policy_name="routine_support",
        parser_domain_hints=["routine"],
        effective_domain="routine",
    )

    assert selected == [
        "Приём лекарств в последнее время был неполным.",
        "Повседневная рутина в последние дни давалась тяжело.",
        "Контроль жидкости остаётся важной частью повседневной рутины.",
    ]


async def test_get_rendered_context_sections_tracks_real_prompt_sections():
    context = {
        "patient_summary_prompt": [
            "? ????????? ??? ??? ?????????.",
        ],
        "recent_vitals": ["BP 120/80"],
        "sleep_summary": ["???: ??????? 5.2?"],
        "rag_context": ["?? ???? ????? ???? ????."],
    }

    rendered = context_builder.get_rendered_context_sections(context)

    assert rendered == ["patient_summary_prompt", "rag_context"]


async def test_build_role_specific_rag_views_cleans_routine_fragments():
    rag_context = [
        "Урок «Сон». Релевантный фрагмент: Урок: Сон Тема: son Тип карточки: text Раздел: actions Попробуйте одно из этого Сделай короткую паузу и снизь темп на ближайшие часы."
    ]
    rag_grounding_items = [
        {
            "rag_index": 0,
            "lesson_title": "Сон",
            "chunk": "Урок: Сон\nТема: son\nТип карточки: text\nРаздел: actions\nПопробуйте одно из этого\nСделай короткую паузу и снизь темп на ближайшие часы.",
            "practice": {"id": 7, "title": "Дыхательная практика"},
        }
    ]

    views = context_builder._build_role_specific_rag_views(rag_context, rag_grounding_items)

    assert views["education"] == rag_context
    assert views["routine"] == ["Попробуйте одно из этого Сделай короткую паузу и снизь темп на ближайшие часы."]
    assert "Урок:" not in views["routine"][0]
    assert views["psych_support"] == ["Практика по теме: Дыхательная практика. Связанный материал: Сон"]


async def test_make_cta_metadata_prefers_practice_after_passed_test():
    cta = context_builder._make_cta_metadata(
        lesson_id=11,
        lesson_code="sleep",
        lesson_title="Сон",
        is_read=True,
        is_completed=True,
        has_passed_test=True,
        practice={"id": 5, "title": "Дыхание 4-6"},
    )

    assert cta["cta_type"] == "practice"
    assert cta["cta_reason"] == "lesson_mastered"
    assert cta["cta_target"]["practice_id"] == 5


async def test_make_cta_metadata_keeps_lesson_when_not_mastered():
    cta = context_builder._make_cta_metadata(
        lesson_id=11,
        lesson_code="sleep",
        lesson_title="Сон",
        is_read=True,
        is_completed=False,
        has_passed_test=False,
        practice={"id": 5, "title": "Дыхание 4-6"},
    )

    assert cta["cta_type"] == "lesson"
    assert cta["cta_reason"] == "lesson_needs_review"


async def test_make_cta_metadata_returns_lesson_for_unread_lesson():
    cta = context_builder._make_cta_metadata(
        lesson_id=11,
        lesson_code="sleep",
        lesson_title="Сон",
        is_read=False,
        is_completed=False,
        has_passed_test=False,
        practice=None,
    )

    assert cta["cta_type"] == "lesson"
    assert cta["cta_reason"] == "lesson_unread"


async def test_build_role_specific_rag_views_adds_standalone_psych_support_items():
    views = context_builder._build_role_specific_rag_views(
        [],
        [],
        ["Практика: Квадратное дыхание. Зачем: Остановить нарастающую тревогу."],
    )

    assert views["psych_support"] == [
        "Практика: Квадратное дыхание. Зачем: Остановить нарастающую тревогу."
    ]
