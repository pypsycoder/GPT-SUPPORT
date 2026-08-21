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

import copy
import os
from typing import Any

from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

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


# Живым прогоном (шаг 7, после обмена с функцией в истории) поймано: GigaChat
# иногда генерирует спецтокен вместо ASCII-кавычки — валидный на вид JSON,
# ключи и значения на месте, но `"` заменена на буквальную строку
# `<|superquote|>`. Судя по всему, артефакт токенизатора, а не поломанная
# структура ответа — воспроизводится именно после function_call в истории,
# не на обычных structured()-вызовах. Лечится заменой перед парсингом.
_SUPERQUOTE_TOKEN = "<|superquote|>"


def strip_fence(text: str) -> str:
    """Снимает ```-обёртку и известные артефакты токенизатора перед парсингом JSON."""
    cleaned = str(text or "").strip()
    if _SUPERQUOTE_TOKEN in cleaned:
        cleaned = cleaned.replace(_SUPERQUOTE_TOKEN, '"')
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


def all_required(model: type[BaseModel], *, name: str | None = None) -> type[BaseModel]:
    """Копия модели без дефолтов — то есть с полным ``required``.

    Нужна, чтобы прогнать строгую и мягкую схему одним и тем же кодом. Ручная
    копия модели рядом с оригиналом разъедется на первом же новом поле, поэтому
    поля берутся из оригинала, и у них снимаются только дефолты.

    Наследование от исходной модели сохраняет ``model_config`` и валидаторы:
    меняется ровно одна переменная — состав ``required``.
    """
    fields: dict[str, Any] = {}
    for field_name, info in model.model_fields.items():
        clone: FieldInfo = copy.deepcopy(info)
        clone.default = PydanticUndefined
        clone.default_factory = None
        fields[field_name] = (clone.annotation, clone)

    return create_model(  # type: ignore[call-overload]
        name or f"Required{model.__name__}",
        __base__=model,
        **fields,
    )


def assert_required_present(schema: dict[str, Any]) -> None:
    """Страж правила №2: схема без ``required`` не соблюдается моделью."""
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    missing = sorted(set(properties) - set(required))
    if missing:
        raise ValueError(f"json schema without required fields: {', '.join(missing)}")
