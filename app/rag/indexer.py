"""
RAG Indexer — индексация карточек уроков для Hybrid RAG.

Запуск: python -m app.rag.indexer

Алгоритм:
1. Достать все карточки из education.lesson_cards + JOIN lessons
2. Сформировать chunk_text = "{lesson_title} | {card_type}: {content_md[:500]}"
3. Вызвать GigaChat Embeddings API батчами по 20 (ограничение API)
4. Сохранить в education.lesson_embeddings
5. Логировать прогресс
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import httpx
from sqlalchemy import text

# Добавляем корень проекта в sys.path для запуска как скрипта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logger = logging.getLogger("rag.indexer")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

EMBEDDINGS_URL = "https://gigachat.devices.sberbank.ru/api/v1/embeddings"
BATCH_SIZE = 20


async def _get_embeddings(texts: list[str], token: str) -> list[list[float]]:
    """
    Вызывает GigaChat Embeddings API для списка текстов.

    Returns:
        Список векторов в том же порядке, что и texts.
    """
    from app.llm.pool import _get_ssl_verify

    verify = _get_ssl_verify()
    async with httpx.AsyncClient(verify=verify, timeout=60.0) as client:
        resp = await client.post(
            EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"model": "Embeddings", "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()

    # API может вернуть элементы не по порядку — сортируем по index
    items = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in items]


def _vec_to_pg(v: list[float]) -> str:
    """Сериализует вектор в JSON-строку для хранения в TEXT-колонке."""
    import json
    return json.dumps(v)


async def run_indexer() -> None:
    from dotenv import load_dotenv

    load_dotenv()

    from core.db.session import async_session_factory
    from app.llm.pool import pool

    async with async_session_factory() as db:
        # Получаем токен через существующий пул
        gc_client = await pool.get_available("lite")
        token = await gc_client._get_access_token()

        # Достаём все активные карточки с заголовком урока
        result = await db.execute(
            text("""
                SELECT lc.id,
                       lc.lesson_id,
                       lc.order_index AS card_index,
                       lc.card_type,
                       lc.content_md,
                       l.title        AS lesson_title
                FROM education.lesson_cards lc
                JOIN education.lessons l ON l.id = lc.lesson_id
                WHERE l.is_active = true
                ORDER BY lc.lesson_id, lc.order_index
            """)
        )
        cards = result.fetchall()
        total = len(cards)
        logger.info("[indexer] Найдено %d карточек для индексации", total)

        if total == 0:
            logger.info("[indexer] Нечего индексировать. Выход.")
            return

        # Очищаем старые эмбеддинги перед переиндексацией
        await db.execute(text("DELETE FROM education.lesson_embeddings"))
        await db.commit()
        logger.info("[indexer] Старые эмбеддинги очищены")

        # Подготавливаем чанки: (lesson_id, card_index, chunk_text)
        chunks: list[tuple[int, int, str]] = []
        for card in cards:
            chunk_text = (
                f"{card.lesson_title} | {card.card_type}: {card.content_md[:500]}"
            )
            chunks.append((card.lesson_id, card.card_index, chunk_text))

        # Батчевая отправка в Embeddings API и сохранение
        indexed = 0
        for batch_start in range(0, total, BATCH_SIZE):
            batch = chunks[batch_start : batch_start + BATCH_SIZE]
            texts = [c[2] for c in batch]

            try:
                embeddings = await _get_embeddings(texts, token)
            except Exception as exc:
                logger.warning(
                    "[indexer] Ошибка API на батче %d, обновляем токен и повторяем: %s",
                    batch_start,
                    exc,
                )
                token = await gc_client._get_access_token()
                embeddings = await _get_embeddings(texts, token)

            for i, (lesson_id, card_index, chunk_text) in enumerate(batch):
                emb_str = _vec_to_pg(embeddings[i])
                await db.execute(
                    text("""
                        INSERT INTO education.lesson_embeddings
                            (lesson_id, card_index, chunk_text, embedding)
                        VALUES
                            (:lesson_id, :card_index, :chunk_text, :embedding)
                    """),
                    {
                        "lesson_id": lesson_id,
                        "card_index": card_index,
                        "chunk_text": chunk_text,
                        "embedding": emb_str,
                    },
                )

            await db.commit()
            indexed += len(batch)
            logger.info("[indexer] indexed %d/%d cards", indexed, total)

    logger.info("[indexer] Готово. Проиндексировано %d карточек.", total)


if __name__ == "__main__":
    asyncio.run(run_indexer())
