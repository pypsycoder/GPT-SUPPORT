"""
education_parser.py — парсер md-файлов уроков, без внешних зависимостей.
Импортируется как в import_md_v2.py, так и в тестах напрямую.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


VALID_CARD_TYPES = {
    "recognition", "mechanism", "empowerment",
    "deepdive", "actions", "anchor", "text",
}

CARD_TYPE_RE = re.compile(r"^\[(\w+)\]\s*(.+)$")
ACTION_LINE_RE = re.compile(r"^>\s*(.+)$")


@dataclass
class CardData:
    card_type: str
    title: str
    content_md: str
    actions_json: Optional[str] = None


def _parse_card_type_and_title(heading_line: str) -> tuple[str, str]:
    stripped = heading_line.lstrip("#").strip()
    m = CARD_TYPE_RE.match(stripped)
    if m:
        raw_type = m.group(1).lower()
        title = m.group(2).strip()
        if raw_type not in VALID_CARD_TYPES:
            return "text", stripped
        return raw_type, title
    return "text", stripped


def _parse_actions(lines: List[str]) -> tuple[str, Optional[str]]:
    action_items: List[str] = []
    content_lines: List[str] = []

    for line in lines:
        m = ACTION_LINE_RE.match(line)
        if m:
            action_items.append(m.group(1).strip())
        else:
            content_lines.append(line)

    while content_lines and not content_lines[0].strip():
        content_lines.pop(0)
    while content_lines and not content_lines[-1].strip():
        content_lines.pop()

    content_md = "\n".join(content_lines).strip()
    actions_json = json.dumps(action_items, ensure_ascii=False) if action_items else None
    return content_md, actions_json


def parse_lesson_markdown(md_text: str) -> List[CardData]:
    lines = md_text.splitlines()
    blocks: List[tuple[str, List[str]]] = []
    current_heading: Optional[str] = None
    current_block: List[str] = []

    for line in lines:
        if line.strip().startswith("## "):
            if current_heading is not None:
                blocks.append((current_heading, current_block))
            current_heading = line.strip()
            current_block = []
        elif line.strip().startswith("# "):
            continue  # заголовок урока — пропускаем
        else:
            if current_heading is not None:
                current_block.append(line)

    if current_heading is not None:
        blocks.append((current_heading, current_block))

    cards: List[CardData] = []

    for heading_line, block_lines in blocks:
        while block_lines and not block_lines[0].strip():
            block_lines.pop(0)
        while block_lines and not block_lines[-1].strip():
            block_lines.pop()

        card_type, title = _parse_card_type_and_title(heading_line)

        if card_type == "actions":
            content_md, actions_json = _parse_actions(block_lines)
        else:
            content_md = "\n".join(block_lines).strip()
            actions_json = None

        if not content_md and not actions_json:
            continue

        cards.append(CardData(
            card_type=card_type,
            title=title,
            content_md=content_md,
            actions_json=actions_json,
        ))

    return cards


def validate_lesson_md(md_path: Path) -> dict:
    md_path = Path(md_path)
    errors: List[str] = []
    warnings: List[str] = []

    if not md_path.exists():
        return {"ok": False, "errors": [f"Файл не найден: {md_path}"]}

    md_text = md_path.read_text(encoding="utf-8")
    cards = parse_lesson_markdown(md_text)

    if not cards:
        errors.append("Нет ни одной карточки (заголовков ## )")

    type_counts: dict[str, int] = {}
    for card in cards:
        type_counts[card.card_type] = type_counts.get(card.card_type, 0) + 1

        if card.card_type == "actions":
            if not card.actions_json:
                warnings.append(
                    f"[actions] '{card.title}': нет строк '> ...'"
                )
            else:
                items = json.loads(card.actions_json)
                if len(items) < 3:
                    warnings.append(
                        f"[actions] '{card.title}': рекомендуется 3–4 варианта, найдено {len(items)}"
                    )

    recommended = {"recognition", "actions", "anchor"}
    missing = recommended - set(type_counts.keys())
    if missing:
        warnings.append(f"Рекомендуемые типы карточек отсутствуют: {missing}")

    return {
        "ok": len(errors) == 0,
        "card_count": len(cards),
        "type_counts": type_counts,
        "errors": errors,
        "warnings": warnings,
    }
