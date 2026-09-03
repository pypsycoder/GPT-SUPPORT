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
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined


# Найдено вживую (шаг 6-7, см. router_l2.py и памятку проекта): без этой
# явной инструкции модель — особенно на lite или после function_call в
# истории — норовит ответить голым значением или строкой "поле: значение"
# вместо JSON, и валидация падает на первой попытке. Формулировка была
# независимо продублирована как минимум в трёх местах
# (agent/prompts.py, agent/judge.py, router_l2.py) с расхождениями в точной
# фразе — здесь один источник правды, остальные ссылаются на него.
JSON_ONLY_INSTRUCTION = (
    "Верни ОДИН JSON-объект строго по переданной схеме, без markdown и без пояснений."
)


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


def response_format_for(model: type[BaseModel], *, provider: str = "sber") -> dict[str, Any]:
    """Готовое тело ``response_format`` для ``/chat/completions``.

    Форма зависит от провайдера:

    * **sber** — ``{"type": "json_schema", "schema": {...}, "strict": true}``
      (документация Сбера).
    * **cloudru** — OpenAI-канон: схема вложена в ``json_schema`` с обязательным
      ``name``. Плоскую сберовскую форму шлюз Cloud.ru отклоняет с 400.
    """
    schema = json_schema_for(model)
    if provider == "cloudru":
        return {
            "type": "json_schema",
            "json_schema": {"name": model.__name__, "schema": schema, "strict": True},
        }
    return {
        "type": "json_schema",
        "schema": schema,
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
