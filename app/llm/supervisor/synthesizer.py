"""Build one user-facing response from deterministic content blocks."""

from __future__ import annotations

from app.llm.supervisor.models import ContentBlock

_ORDER = {
    "validation": 0,
    "safety": 1,
    "clarification": 1,
    "explanation": 2,
    "action": 3,
    "follow_up": 4,
}


class ResponseSynthesizer:
    """Assembles the final user-facing response."""

    def synthesize(self, content_blocks: list[ContentBlock]) -> str:
        seen_keys: set[str] = set()
        seen_texts: set[str] = set()
        ordered = sorted(
            [dict(block) for block in content_blocks if str(block.get("text") or "").strip()],
            key=lambda item: (_ORDER.get(str(item.get("kind")), 99), str(item.get("text"))),
        )
        unique_texts: list[str] = []

        for block in ordered:
            dedupe_key = str(block.get("dedupe_key") or "").strip()
            text = str(block.get("text") or "").strip()
            if dedupe_key and dedupe_key in seen_keys:
                continue
            if text in seen_texts:
                continue
            if dedupe_key:
                seen_keys.add(dedupe_key)
            seen_texts.add(text)
            unique_texts.append(text)

        return " ".join(unique_texts).strip()
