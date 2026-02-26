"""
Parser — парсинг неструктурированного текста пациента в структурированные данные.

Использует GigaChat-2 (lite) для извлечения структур из свободного текста.
НЕ записывает данные в БД — только парсит и возвращает dict.

Функция:
  parse_patient_message(text, patient_id, db) -> dict
    Поля ответа: vitals, medications, practices, mood, domain_hints
    При ошибке парсинга → пустой dict.
    Если все поля пусты → добавляет needs_clarification=True.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("gpt-support-llm.parser")

# ---------------------------------------------------------------------------
# Системный промпт для парсинга
# ---------------------------------------------------------------------------

PARSER_PROMPT = """Ты парсер медицинских данных. Извлеки из текста пациента структурированные данные в JSON. Отвечай ТОЛЬКО валидным JSON, без пояснений.

Формат ответа:
{
  "vitals": [{"type": "BP", "value": "155/95", "time": "morning"}],
  "medications": [{"name": "название", "taken": true}],
  "practices": [{"name": "название", "completed": true}],
  "mood": "good|neutral|bad|unknown",
  "domain_hints": ["sleep", "emotion"]
}

Если данных нет — возвращай пустые массивы.
Текст пациента: {text}"""


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------


async def parse_patient_message(
    text: str,
    patient_id: int,
    db: AsyncSession,
) -> dict:
    """
    Парсит сообщение пациента в структурированные данные через GigaChat-2 (lite).

    Args:
        text:       свободный текст сообщения пациента
        patient_id: ID пациента (для логирования)
        db:         AsyncSession (не используется для записи)

    Returns:
        dict с полями: vitals, medications, practices, mood, domain_hints
        При ошибке парсинга → пустой dict {}.
        Если все поля пусты → добавляет needs_clarification=True.
    """
    from app.llm.pool import pool

    prompt = PARSER_PROMPT.format(text=text)
    messages = [{"role": "user", "content": prompt}]
    system = "Ты медицинский парсер. Отвечай только валидным JSON."

    try:
        client = await pool.get_available("lite")
        raw_text, _, _, _ = await client.call(messages, system)
    except Exception as exc:
        logger.warning("[parser] patient=%d ошибка LLM вызова: %s", patient_id, exc)
        return {}

    # Извлекаем JSON — иногда модель оборачивает в ```json ... ```
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        # Убираем первую строку (```json или ```) и последнюю (```)
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        raw_text = "\n".join(inner).strip()

    try:
        data: dict = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning(
            "[parser] patient=%d не удалось распарсить JSON: %.200s",
            patient_id, raw_text,
        )
        return {}

    # Проверяем: если все поля пусты — запрашиваем уточнение
    vitals = data.get("vitals", [])
    medications = data.get("medications", [])
    practices = data.get("practices", [])
    mood = data.get("mood", "unknown")
    domain_hints = data.get("domain_hints", [])

    all_empty = (
        not vitals
        and not medications
        and not practices
        and mood == "unknown"
        and not domain_hints
    )
    if all_empty:
        data["needs_clarification"] = True

    return data
