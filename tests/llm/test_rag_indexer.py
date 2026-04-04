from __future__ import annotations

import pytest

from app.rag.indexer import _vec_to_pgvector_literal


pytestmark = [pytest.mark.unit]


def test_vec_to_pgvector_literal_formats_vector():
    assert _vec_to_pgvector_literal([1, 2.5, -3]) == "[1.0,2.5,-3.0]"
