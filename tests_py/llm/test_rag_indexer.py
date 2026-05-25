from __future__ import annotations

import pytest

from app.rag.indexer import _build_chunk_text, _vec_to_pgvector_literal


pytestmark = [pytest.mark.unit]


def test_vec_to_pgvector_literal_formats_vector():
    assert _vec_to_pgvector_literal([1, 2.5, -3]) == "[1.0,2.5,-3.0]"


def test_build_chunk_text_normalizes_markdown():
    chunk = _build_chunk_text(
        lesson_title="Сон",
        lesson_topic="sleep",
        card_type="text",
        content_md="## [actions]\n\n> Сделайте три медленных выдоха\n\n**Потом** попробуйте лечь снова.",
    )

    assert "Урок: Сон" in chunk
    assert "Тема: sleep" in chunk
    assert "Раздел: actions" in chunk
    assert "Сделайте три медленных выдоха" in chunk
    assert "**" not in chunk
