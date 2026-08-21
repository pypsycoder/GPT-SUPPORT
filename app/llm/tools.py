"""
Реестр инструментов для нативного function calling GigaChat (шаг 7).

Зачем это вместо предзагрузки: `_load_education_grounding()` сейчас тянет
RAG на каждый ход с текстом длиннее 10 символов — почти всегда, хотя
`intent == "education"` встречается только в ~17% размеченных сообщений
(`LLM_test/cases/intent_labels.json`). С функцией модель сама решает, нужен
ли ей поиск по базе уроков, и просит его только когда действительно нужен.

Контракт вызова инструмента для GigaChat: `name`, `description`,
`parameters` (JSON Schema). `parameters` строятся через уже существующий
`structured.json_schema_for()` — тот же плоский формат, что и у
`response_format`, ничего нового изобретать не нужно.

Ошибки инструмента не поднимаются наружу из `invoke()`: модель должна
увидеть ошибку как данные и решить, что делать. Падение цикла из-за кривого
аргумента — худший сценарий в проде (00_MANUAL.md, часть 7.3).
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field, ValidationError

from app.llm import structured

logger = logging.getLogger("gpt-support-llm.tools")

ENV_FLAG = "LLM_AGENT_TOOLS"
_TRUTHY = frozenset({"1", "true", "yes", "on"})

Handler = Callable[..., Awaitable[Any]]


def agent_tools_enabled() -> bool:
    return str(os.getenv(ENV_FLAG, "")).strip().lower() in _TRUTHY


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Handler

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": structured.json_schema_for(self.args_model),
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        args_model: type[BaseModel],
    ) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            self._tools[name] = Tool(name=name, description=description, args_model=args_model, handler=fn)
            return fn

        return deco

    def specs(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        """Описания функций едут в каждый запрос и стоят токенов — отдавать
        только те, что релевантны текущему ходу (пока один инструмент, это
        не проблема; при следующем — фильтровать по интенту)."""
        items = self._tools.values() if names is None else [
            self._tools[n] for n in names if n in self._tools
        ]
        return [t.spec() for t in items]

    async def invoke(self, name: str, raw_args: dict[str, Any], **ctx: Any) -> str:
        """Выполнить инструмент, вернуть строку для сообщения ``role="function"``.

        Никогда не поднимает исключение — падение цикла из-за кривого
        аргумента или сбоя внутри хендлера хуже, чем модель, увидевшая
        ошибку как данные и решившая, что делать дальше.
        """
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"unknown_tool:{name}"}, ensure_ascii=False)

        try:
            args = tool.args_model.model_validate(raw_args)
        except ValidationError as exc:
            return json.dumps(
                {"error": "invalid_arguments", "detail": exc.errors(include_url=False)[:3]},
                ensure_ascii=False,
                default=str,
            )

        try:
            sig = inspect.signature(tool.handler)
            kwargs = {k: v for k, v in ctx.items() if k in sig.parameters}
            result = await tool.handler(args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — сознательно широкий except
            logger.exception("[tools] %s failed", name)
            return json.dumps({"error": "tool_failed", "detail": str(exc)[:200]}, ensure_ascii=False)

        if isinstance(result, BaseModel):
            return result.model_dump_json()
        return json.dumps(result, ensure_ascii=False, default=str)


registry = ToolRegistry()


# --------------------------------------------------------------------------- #
# search_education
# --------------------------------------------------------------------------- #

class SearchEducationArgs(BaseModel):
    query: str = Field(
        max_length=200,
        description="Что ищем в базе психообразовательных материалов, на русском.",
    )


class EducationHit(BaseModel):
    title: str
    snippet: str


class SearchEducationResult(BaseModel):
    hits: list[EducationHit]


@registry.register(
    "search_education",
    "Поиск по базе психообразовательных материалов для пациентов на программном "
    "гемодиализе (питание, режим, самочувствие, психологические темы). Вызывай, "
    "когда пациенту нужен конкретный обучающий материал или проверяемый факт, "
    "а не для обычного разговора.",
    SearchEducationArgs,
)
async def _search_education(args: SearchEducationArgs, *, patient_id: int, db: Any) -> SearchEducationResult:
    from app.llm.context_builder import _clip_rag_fragment
    from app.rag.retriever import retrieve_relevant_modules_with_meta

    result = await retrieve_relevant_modules_with_meta(args.query, patient_id, db, top_k=3)
    hits = [
        EducationHit(title=str(m.get("title") or ""), snippet=_clip_rag_fragment(str(m.get("chunk") or "")))
        for m in result.get("modules", [])
    ]
    return SearchEducationResult(hits=hits)
