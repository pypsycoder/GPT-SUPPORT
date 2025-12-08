from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import yaml


ROOT_DIR = Path(__file__).resolve().parents[3]
CONTENT_PATH = ROOT_DIR / "content" / "TOBOL.MD"


def _extract_diagnostic_code(md_text: str) -> dict:
    """Извлекаем YAML-блок diagnostic_code из Markdown."""

    match = re.search(r"(^diagnostic_code:.*)", md_text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError("Не найден блок diagnostic_code в TOBOL.MD")

    yaml_text = md_text[match.start() :]
    payload = yaml.safe_load(yaml_text)
    if not isinstance(payload, dict) or "diagnostic_code" not in payload:
        raise ValueError("Не удалось распарсить diagnostic_code из TOBOL.MD")

    return payload["diagnostic_code"]


def _parse_questions(md_text: str) -> List[Dict[str, object]]:
    """Парсим перечень утверждений по разделам I–XII."""

    questions: List[Dict[str, object]] = []
    current_section: Tuple[str, str] | None = None

    for line in md_text.splitlines():
        if line.strip().startswith("# Оценка результатов"):
            break

        heading = re.match(r"^###\s+([IVX]+)\.\s*(.*)$", line.strip())
        if heading:
            current_section = (heading.group(1), heading.group(2).strip())
            continue

        match = re.match(r"^(\d+)\.\s*(.+)$", line.strip())
        if current_section and match:
            option_id, text = match.groups()
            question_id = f"{current_section[0]}_{option_id}"
            questions.append(
                {
                    "id": question_id,
                    "section": current_section[0],
                    "section_title": current_section[1],
                    "text": text.strip(),
                    # единственный вариант — отметить утверждение
                    "options": [
                        {
                            "id": option_id,
                            "text": text.strip(),
                        }
                    ],
                }
            )

    if not questions:
        raise ValueError("Не удалось распарсить вопросы шкалы ТОБОЛ")

    return questions


@lru_cache()
def load_tobol_config() -> Dict[str, object]:
    """Загружает конфиг шкалы ТОБОЛ из Markdown."""

    md_text = CONTENT_PATH.read_text(encoding="utf-8")
    diagnostic_code = _extract_diagnostic_code(md_text)
    questions = _parse_questions(md_text)

    return {
        "code": "TOBOL",
        "title": "ТОБОЛ — Тип отношения к болезни",
        "version": "1.0",
        "questions": questions,
        "diagnostic_code": diagnostic_code,
    }


TOBOL_CONFIG = load_tobol_config()

