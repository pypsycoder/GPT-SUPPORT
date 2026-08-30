"""build_education_cta — CTA-кнопка «Открыть урок» под ответом агента."""

from __future__ import annotations

import pytest

from app.llm import context_builder as cb


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


def _patch(monkeypatch, *, modules, grounding):
    async def _retrieve(query, patient_id, db, top_k=3):
        return {"modules": list(modules)}

    async def _grounding(patient_id, modules_arg, db):
        return list(grounding)

    monkeypatch.setattr(
        "app.rag.retriever.retrieve_relevant_modules_with_meta", _retrieve
    )
    monkeypatch.setattr(cb, "_build_rag_grounding_items", _grounding)


async def test_returns_frontend_shape_for_unread_lesson(monkeypatch):
    _patch(
        monkeypatch,
        modules=[{"lesson_id": 12, "title": "Жидкость", "code": "02"}],
        grounding=[
            {
                "lesson_title": "Жидкость",
                "cta": {
                    "cta_type": "lesson",
                    "cta_label": "Жидкость",
                    "cta_target": {"lesson_id": 12, "lesson_code": "02"},
                },
            }
        ],
    )

    cta = await cb.build_education_cta(1, "сколько можно пить воды", db=object())

    assert cta == {"type": "lesson", "lesson_id": 12, "label": "Жидкость"}


async def test_none_when_no_modules(monkeypatch):
    _patch(monkeypatch, modules=[], grounding=[])
    assert await cb.build_education_cta(1, "привет как дела", db=object()) is None


async def test_none_when_no_lesson_cta(monkeypatch):
    _patch(
        monkeypatch,
        modules=[{"lesson_id": 5, "title": "T", "code": "01"}],
        grounding=[{"cta": {"cta_type": "none", "cta_target": None}}],
    )
    assert await cb.build_education_cta(1, "какой-то запрос", db=object()) is None


async def test_none_on_too_short_query(monkeypatch):
    called = False

    async def _retrieve(*a, **kw):
        nonlocal called
        called = True
        return {"modules": []}

    monkeypatch.setattr(
        "app.rag.retriever.retrieve_relevant_modules_with_meta", _retrieve
    )
    assert await cb.build_education_cta(1, "ок", db=object()) is None
    assert called is False
