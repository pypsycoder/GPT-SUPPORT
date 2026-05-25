from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_CACHE_TTL_SECONDS = 60.0
_capabilities_cache: dict[str, object] = {
    "expires_at": 0.0,
    "value": None,
}


async def get_rag_backend_info(db: AsyncSession) -> dict[str, object]:
    now = time.monotonic()
    cached_value = _capabilities_cache.get("value")
    expires_at = float(_capabilities_cache.get("expires_at", 0.0) or 0.0)
    if cached_value is not None and now < expires_at:
        return dict(cached_value)

    extension_result = await db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_extension
                WHERE extname = 'vector'
            )
            """
        )
    )
    extension_installed = bool(extension_result.scalar())

    vector_column_result = await db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'education'
                  AND table_name = 'lesson_embeddings'
                  AND column_name = 'embedding_vector'
            )
            """
        )
    )
    vector_column_present = bool(vector_column_result.scalar())

    vector_index_result = await db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'education'
                  AND tablename = 'lesson_embeddings'
                  AND indexdef ILIKE '%embedding_vector%'
            )
            """
        )
    )
    vector_index_present = bool(vector_index_result.scalar())

    backend = "pgvector" if extension_installed and vector_column_present else "python_cosine"
    blocker = None
    if not extension_installed:
        blocker = "pgvector_extension_missing"
    elif not vector_column_present:
        blocker = "embedding_vector_column_missing"
    elif not vector_index_present:
        blocker = "embedding_vector_index_missing"

    info = {
        "backend": backend,
        "extension_installed": extension_installed,
        "vector_column_present": vector_column_present,
        "vector_index_present": vector_index_present,
        "blocker": blocker,
    }

    _capabilities_cache["value"] = dict(info)
    _capabilities_cache["expires_at"] = now + _CACHE_TTL_SECONDS
    return info


def reset_rag_backend_info_cache() -> None:
    _capabilities_cache["value"] = None
    _capabilities_cache["expires_at"] = 0.0
