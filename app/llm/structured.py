"""
Структурный вывод GigaChat: ``response_format={"type": "json_schema", ...}``.

Заменяет самописный парсинг «поле: значение» с ретраями. Матчасть:
https://developers.sber.ru/docs/ru/gigachat/guides/structured-output

Три правила, о которые легко разбиться:

1. **``$ref`` ломает strict-режим.** Pydantic для вложенных моделей и Enum
   генерирует ``$defs`` + ``$ref``; ``json_schema_for()`` их инлайнит.
   Держите схемы плоскими — это ещё и дешевле по токенам.
2. **Без массива ``required`` модель вернёт произвольный JSON даже при
   ``strict: true``.** Прямо сказано в документации. ``json_schema_for()``
   это обеспечивает через Pydantic (все поля обязательные).
3. **Не смешивать ``functions`` и ``response_format`` в одном запросе.**
   Поведение непредсказуемо.

Модуль — новая ветка рядом со старой. Включается ``LLM_STRUCTURED_OUTPUT=1``;
при выключенном флаге ``policy`` собирает и парсит карточки как раньше.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

ENV_FLAG = "LLM_STRUCTURED_OUTPUT"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


# GigaChat-2 (тир lite) не соблюдает response_format: на схемах от шести полей
# возвращает текстовую карточку вместо JSON. Валидация падает, срабатывает
# repair — и вызов стоит вдвое дороже. Замер на пилоте: lite 3 починки из 3
# карточек, pro — 0 из 5. Трёхпольная схема делегации на lite проходит, но
# полагаться на это нельзя.
UNSUPPORTED_TIERS = frozenset({"lite"})


def structured_enabled() -> bool:
    """Включён ли структурный вывод (флаг окружения)."""
    return str(os.getenv(ENV_FLAG, "")).strip().lower() in _TRUTHY


def structured_enabled_for_tier(model_tier: str | None) -> bool:
    """Структурный вывод для конкретного тира.

    Тир, который не держит схему, откатывается на текстовые карточки — вместе
    с форматом системного промпта, иначе модель получит инструкцию про JSON,
    а парсить мы будем строки.
    """
    if not structured_enabled():
        return False
    return str(model_tier or "").strip().lower() not in UNSUPPORTED_TIERS


def strip_fence(text: str) -> str:
    """Снимает ```-обёртку, если модель всё-таки её поставила."""
    cleaned = str(text or "").strip()
    if not cleaned.startswith("```"):
        return cleaned
    cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.rstrip().endswith("```"):
        cleaned = cleaned.rstrip()[:-3]
    return cleaned.strip()


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic → JSON Schema в виде, который переваривает GigaChat.

    Инлайнит ``$defs``: вложенные модели и Enum через ``$ref`` местами ломают
    strict-режим. Ключи схемы берутся по alias — карточки описаны русскими
    именами полей, теми же, что понимают системные промпты.
    """
    schema = model.model_json_schema(by_alias=True)
    defs = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs.get(ref.split("/")[-1], {})
                merged = dict(inline(target))
                merged.update({k: v for k, v in node.items() if k != "$ref"})
                return merged
            return {key: inline(value) for key, value in node.items()}
        if isinstance(node, list):
            return [inline(value) for value in node]
        return node

    schema = inline(schema)
    schema.setdefault("additionalProperties", False)
    schema.pop("title", None)
    # Pydantic дублирует имя поля в "title" — для модели это шум, а платим за него
    # на каждом вызове.
    for prop in (schema.get("properties") or {}).values():
        if isinstance(prop, dict):
            prop.pop("title", None)
    return schema


def response_format_for(model: type[BaseModel]) -> dict[str, Any]:
    """Готовое тело ``response_format`` для ``/chat/completions``."""
    return {
        "type": "json_schema",
        "schema": json_schema_for(model),
        "strict": True,
    }


def assert_required_present(schema: dict[str, Any]) -> None:
    """Страж правила №2: схема без ``required`` не соблюдается моделью."""
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    missing = sorted(set(properties) - set(required))
    if missing:
        raise ValueError(f"json schema without required fields: {', '.join(missing)}")
