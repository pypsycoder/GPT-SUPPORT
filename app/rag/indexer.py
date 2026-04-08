"""
RAG Indexer - builds lesson embeddings for educational cards.

Run with: python -m app.rag.indexer
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys

from sqlalchemy import text

from app.llm.errors import LLMResponseError, LLMTransportError
from app.llm.http import request_json_with_policy


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logger = logging.getLogger("rag.indexer")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

EMBEDDINGS_URL = "https://gigachat.devices.sberbank.ru/api/v1/embeddings"
BATCH_SIZE = 20
_HEADING_RE = re.compile(r"^##\s*\[([^\]]+)\]\s*", re.MULTILINE)
_MARKDOWN_REPLACEMENTS = (
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"\*([^*]+)\*"), r"\1"),
    (re.compile(r"^>\s*", re.MULTILINE), ""),
    (re.compile(r"\[(.*?)\]\((.*?)\)"), r"\1"),
)


async def _get_embeddings(texts: list[str], token: str) -> list[list[float]]:
    try:
        data = await request_json_with_policy(
            "embeddings",
            method="POST",
            url=EMBEDDINGS_URL,
            operation="indexer embeddings",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json_body={"model": "Embeddings", "input": texts},
        )
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMResponseError("indexer embeddings payload is invalid") from exc


def _vec_to_pg(v: list[float]) -> str:
    import json

    return json.dumps(v)


def _vec_to_pgvector_literal(v: list[float]) -> str:
    return "[" + ",".join(str(float(item)) for item in v) + "]"


def _normalize_card_text(content_md: str) -> tuple[str | None, str]:
    section_name: str | None = None
    heading_match = _HEADING_RE.search(content_md)
    if heading_match:
        section_name = heading_match.group(1).strip().lower()
        content_md = _HEADING_RE.sub("", content_md, count=1)

    cleaned = content_md
    for pattern, replacement in _MARKDOWN_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)

    cleaned = cleaned.replace("\r", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\s+\n", "\n", cleaned)
    cleaned = cleaned.strip()
    return section_name, cleaned


def _build_chunk_text(*, lesson_title: str, lesson_topic: str, card_type: str, content_md: str) -> str:
    section_name, cleaned = _normalize_card_text(content_md)
    parts = [f"Урок: {lesson_title}", f"Тема: {lesson_topic}", f"Тип карточки: {card_type}"]
    if section_name:
        parts.append(f"Раздел: {section_name}")
    parts.append(cleaned)
    return "\n".join(part for part in parts if part).strip()


async def run_indexer() -> None:
    from app.core.config import load_environment
    from app.llm.http import aclose_shared_http_clients
    from app.llm.pool import pool
    from app.rag.capabilities import get_rag_backend_info
    from core.db.session import async_session_factory

    load_environment()

    total = 0
    try:
        async with async_session_factory() as db:
            backend_info = await get_rag_backend_info(db)
            vector_write_enabled = bool(
                backend_info["extension_installed"] and backend_info["vector_column_present"]
            )
            logger.info(
                "[indexer] rag backend readiness backend=%s blocker=%s extension=%s vector_column=%s vector_index=%s vector_write_enabled=%s",
                backend_info["backend"],
                backend_info["blocker"],
                backend_info["extension_installed"],
                backend_info["vector_column_present"],
                backend_info["vector_index_present"],
                vector_write_enabled,
            )
            gc_client = await pool.get_available("lite")
            token = await gc_client._get_access_token()

            result = await db.execute(
                text(
                    """
                    SELECT lc.id,
                           lc.lesson_id,
                           lc.order_index AS card_index,
                           lc.card_type,
                           lc.content_md,
                           l.title        AS lesson_title,
                           l.topic        AS lesson_topic
                    FROM education.lesson_cards lc
                    JOIN education.lessons l ON l.id = lc.lesson_id
                    WHERE l.is_active = true
                    ORDER BY lc.lesson_id, lc.order_index
                    """
                )
            )
            cards = result.fetchall()
            total = len(cards)
            logger.info("[indexer] found %d cards for indexing", total)

            if total == 0:
                logger.info("[indexer] nothing to index")
                return

            await db.execute(text("DELETE FROM education.lesson_embeddings"))
            await db.commit()
            logger.info("[indexer] cleared previous embeddings")

            chunks: list[tuple[int, int, str]] = []
            for card in cards:
                chunk_text = _build_chunk_text(
                    lesson_title=card.lesson_title,
                    lesson_topic=card.lesson_topic,
                    card_type=card.card_type,
                    content_md=card.content_md,
                )
                chunks.append((card.lesson_id, card.card_index, chunk_text))

            indexed = 0
            for batch_start in range(0, total, BATCH_SIZE):
                batch = chunks[batch_start : batch_start + BATCH_SIZE]
                texts = [c[2] for c in batch]

                try:
                    embeddings = await _get_embeddings(texts, token)
                except (LLMTransportError, LLMResponseError) as exc:
                    logger.warning(
                        "[indexer] embeddings failed on batch %d, refreshing token: %s",
                        batch_start,
                        exc,
                    )
                    token = await gc_client._get_access_token()
                    embeddings = await _get_embeddings(texts, token)

                for i, (lesson_id, card_index, chunk_text) in enumerate(batch):
                    emb_str = _vec_to_pg(embeddings[i])
                    params = {
                        "lesson_id": lesson_id,
                        "card_index": card_index,
                        "chunk_text": chunk_text,
                        "embedding": emb_str,
                    }
                    if vector_write_enabled:
                        params["embedding_vector"] = _vec_to_pgvector_literal(embeddings[i])
                        await db.execute(
                            text(
                                """
                                INSERT INTO education.lesson_embeddings
                                    (lesson_id, card_index, chunk_text, embedding, embedding_vector)
                                VALUES
                                    (:lesson_id, :card_index, :chunk_text, :embedding, CAST(:embedding_vector AS vector))
                                """
                            ),
                            params,
                        )
                    else:
                        await db.execute(
                            text(
                                """
                                INSERT INTO education.lesson_embeddings
                                    (lesson_id, card_index, chunk_text, embedding)
                                VALUES
                                    (:lesson_id, :card_index, :chunk_text, :embedding)
                                """
                            ),
                            params,
                        )

                await db.commit()
                indexed += len(batch)
                logger.info("[indexer] indexed %d/%d cards", indexed, total)
    finally:
        await aclose_shared_http_clients()

    logger.info("[indexer] done, indexed %d cards", total)


if __name__ == "__main__":
    asyncio.run(run_indexer())
