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
import re

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
# Утилиты нормализации витальных значений
# ---------------------------------------------------------------------------


def normalize_bp(value: str) -> tuple[int, int] | None:
    """
    Нормализует строку с АД к паре (systolic, diastolic).

    Принимаемые форматы: "120/80", "120\\80", "120-80", "120 80",
    "120 на 80", "120x80", "120X80", "120|80".

    Возвращает (systolic, diastolic) или None при ошибке / вне диапазона.
    Диапазоны: systolic 60–250, diastolic 40–150.
    """
    v = str(value).strip()
    # Текстовый разделитель "на"
    v = re.sub(r"\s+на\s+", "/", v, flags=re.IGNORECASE)
    # Символьные разделители: \, |, x, X, -
    v = re.sub(r"[\\/|xX-]+", "/", v)
    # Пробел между двумя цифрами
    v = re.sub(r"(\d)\s+(\d)", r"\1/\2", v)

    parts = v.split("/")
    if len(parts) < 2:
        return None

    try:
        sys_m = re.match(r"\d+", parts[0].strip())
        dia_m = re.match(r"\d+", parts[1].strip())
        if not sys_m or not dia_m:
            return None
        systolic = int(sys_m.group())
        diastolic = int(dia_m.group())
    except (ValueError, IndexError):
        return None

    if not (60 <= systolic <= 250) or not (40 <= diastolic <= 150):
        return None

    return systolic, diastolic


def normalize_pulse(value: str) -> int | None:
    """
    Нормализует значение пульса.

    Принимает одно число в диапазоне 30–200.
    Если value содержит два числа через разделитель (похоже на АД) — возвращает None.
    """
    v = str(value).strip()
    # Похоже на АД — отклоняем
    if re.search(r"\d[\s/\\|xX-]+\d", v):
        return None
    m = re.match(r"\d+", v)
    if not m:
        return None
    bpm = int(m.group())
    return bpm if 30 <= bpm <= 200 else None


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------


async def parse_patient_message(
    text: str,
    patient_id: int,
) -> dict:
    """
    Парсит сообщение пациента в структурированные данные через GigaChat-2 (lite).

    Args:
        text:       свободный текст сообщения пациента
        patient_id: ID пациента (для логирования)

    Returns:
        dict с полями: vitals, medications, practices, mood, domain_hints
        При ошибке парсинга → пустой dict {}.
        Если все поля пусты → добавляет needs_clarification=True.
    """
    from app.llm.pool import pool

    prompt = PARSER_PROMPT.replace("{text}", text)
    messages = [{"role": "user", "content": prompt}]
    system = "Ты медицинский парсер. Отвечай только валидным JSON."

    try:
        client = await pool.get_available("lite")
        raw_text, _, _, _ = await client.call(messages, system)
    except Exception as exc:
        logger.warning("[parser] LLM call failed: %s", exc)
        return {}

    logger.debug("[parser] raw_text: %.500s", raw_text)

    # Очищаем ответ модели и извлекаем JSON
    raw_text = raw_text.strip()

    # Шаг 1: извлекаем содержимое ```json ... ``` или ``` ... ```
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        inner = lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        raw_text = "\n".join(inner).strip()

    # Шаг 2: вырезаем только фрагмент от первого { до последнего }
    brace_start = raw_text.find("{")
    brace_end = raw_text.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        raw_text = raw_text[brace_start : brace_end + 1]

    # Шаг 3: убираем управляющие символы внутри строковых значений,
    # которые делают JSON невалидным (literal \n, \t, \r внутри "...")
    raw_text = re.sub(
        r'"([^"\\]*(?:\\.[^"\\]*)*)"',
        lambda m: '"' + m.group(1).replace("\n", " ").replace("\r", "").replace("\t", " ") + '"',
        raw_text,
    )

    try:
        data: dict = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("[parser] JSON parse failed: %.500s", raw_text)
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
