"""
Реестр инструментов для нативного function calling GigaChat.

Зачем это вместо «специалистов»
-------------------------------
В текущей схеме GPT-SUPPORT данные достаются заранее и вклеиваются в промпт
на всякий случай: витальные, расписание диализа, прогресс по урокам, RAG.
Модель платит за них всегда, даже когда они не нужны.

С функциями наоборот: модель сама решает, что ей нужно, и просит это.
Один вызов вместо «router + 3 специалиста + composer», а данные подгружаются
только по делу.

Цена: +1 round-trip на каждый вызов инструмента. Выигрыш появляется, когда
инструмент нужен реже, чем в половине запросов. Меряйте, а не верьте на слово.

Контракт функции для GigaChat:
    name, description, parameters (JSON Schema), return_parameters (JSON Schema).
return_parameters не обязателен, но заметно улучшает качество аргументов:
модель понимает, что получит обратно.
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, get_type_hints

from pydantic import BaseModel, ValidationError

from gigachat_client import json_schema_for

logger = logging.getLogger("giga.tools")

Handler = Callable[..., Awaitable[Any]]


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    returns_model: type[BaseModel] | None
    handler: Handler
    # Сколько токенов примерно вернёт. Нужно для бюджета шага.
    est_result_tokens: int = 200

    def spec(self) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": json_schema_for(self.args_model),
        }
        if self.returns_model is not None:
            spec["return_parameters"] = json_schema_for(self.returns_model)
        return spec


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        args_model: type[BaseModel],
        returns_model: type[BaseModel] | None = None,
        *,
        est_result_tokens: int = 200,
    ) -> Callable[[Handler], Handler]:
        def deco(fn: Handler) -> Handler:
            self._tools[name] = Tool(
                name=name,
                description=description,
                args_model=args_model,
                returns_model=returns_model,
                handler=fn,
                est_result_tokens=est_result_tokens,
            )
            return fn
        return deco

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        """
        Описания функций едут в каждый запрос и стоят токенов.
        Отдавайте модели ТОЛЬКО инструменты, релевантные текущему интенту —
        это работа роутера. 12 функций в промпте не только дорого,
        но и заметно снижает точность выбора.
        """
        items = self._tools.values() if names is None else [
            self._tools[n] for n in names if n in self._tools
        ]
        return [t.spec() for t in items]

    async def invoke(self, name: str, raw_args: dict[str, Any], **ctx: Any) -> str:
        """
        Выполнить инструмент и вернуть строку для сообщения с role="function".

        Ошибки НЕ поднимаются наверх: модель должна увидеть ошибку как данные
        и решить, что делать. Падение цикла из-за кривого аргумента —
        худший из возможных сценариев в проде.
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
            logger.exception("tool %s failed", name)
            return json.dumps({"error": "tool_failed", "detail": str(exc)[:200]}, ensure_ascii=False)

        if isinstance(result, BaseModel):
            return result.model_dump_json()
        return json.dumps(result, ensure_ascii=False, default=str)


# --------------------------------------------------------------------------- #
# Примеры инструментов под GPT-SUPPORT
# --------------------------------------------------------------------------- #

registry = ToolRegistry()


class VitalsArgs(BaseModel):
    days: int = 7


class VitalsResult(BaseModel):
    bp_last: str | None = None
    bp_trend: str | None = None
    weight_gain_kg: float | None = None
    note: str | None = None


@registry.register(
    "get_recent_vitals",
    "Витальные показатели пациента за последние дни: АД, пульс, вес, водный баланс. "
    "Вызывать только если пациент спрашивает о своём состоянии или жалуется на симптомы.",
    VitalsArgs,
    VitalsResult,
    est_result_tokens=120,
)
async def _get_recent_vitals(args: VitalsArgs, patient_id: int, db: Any) -> VitalsResult:
    # Здесь — обращение к вашему vitals/crud.py
    raise NotImplementedError("подключите app.vitals.crud")


class LessonSearchArgs(BaseModel):
    query: str
    limit: int = 3


class LessonHit(BaseModel):
    lesson_id: str
    title: str
    snippet: str


class LessonSearchResult(BaseModel):
    hits: list[LessonHit]


@registry.register(
    "search_education",
    "Поиск по базе психообразовательных материалов для пациентов на гемодиализе. "
    "Вызывать, когда нужен конкретный обучающий материал или проверяемый факт.",
    LessonSearchArgs,
    LessonSearchResult,
    est_result_tokens=350,
)
async def _search_education(args: LessonSearchArgs, db: Any) -> LessonSearchResult:
    # Здесь — ваш app/rag/retriever.py (гибрид pgvector + tsvector)
    raise NotImplementedError("подключите app.rag.retriever")


class ScheduleArgs(BaseModel):
    horizon_days: int = 3


class ScheduleResult(BaseModel):
    next_session: str | None = None
    schedule: list[str] = []


@registry.register(
    "get_dialysis_schedule",
    "Ближайшие сеансы гемодиализа пациента. Вызывать при вопросах о планировании дня, "
    "приёме лекарств относительно сеанса, самочувствии до/после диализа.",
    ScheduleArgs,
    ScheduleResult,
    est_result_tokens=80,
)
async def _get_schedule(args: ScheduleArgs, patient_id: int, db: Any) -> ScheduleResult:
    raise NotImplementedError("подключите app.dialysis.crud")
