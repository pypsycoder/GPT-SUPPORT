"""
Тонкий боевой клиент GigaChat под мультиагентную систему.

Отличия от того, что обычно пишут:
  1. X-Session-ID передаётся явно  -> префиксное кэширование контекста.
  2. Учёт precached_prompt_tokens  -> видно, работает кэш или нет.
  3. response_format=json_schema   -> структурный вывод вместо парсинга текста.
  4. functions / function_call     -> нативный tool-calling вместо самодельного.
  5. Глобальный семафор            -> уважает лимит потоков аккаунта.

Проверено по документации GigaChat API (см. 00_MANUAL.md, раздел «Источники»).
Зависимости: httpx, pydantic>=2.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("giga.client")

TModel = TypeVar("TModel", bound=BaseModel)

# Два живых базовых URL. Старый (…devices.sberbank.ru) продолжает работать,
# новый (api.giga.chat) фигурирует в свежих примерах документации.
LEGACY_BASE = "https://gigachat.devices.sberbank.ru/api/v1"
NEW_BASE = "https://api.giga.chat/v1"
OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class GigaError(RuntimeError):
    """Любая ошибка обращения к GigaChat."""


class GigaTransportError(GigaError):
    """Сеть/таймаут — можно ретраить."""


class GigaResponseError(GigaError):
    """API ответил, но ответ непригоден."""


# --------------------------------------------------------------------------- #
# Результаты
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    precached_prompt_tokens: int = 0
    total_tokens: int = 0

    @property
    def cache_hit_ratio(self) -> float:
        """Доля префикса, взятая из кэша. Главная метрика экономии."""
        base = self.prompt_tokens + self.precached_prompt_tokens
        return self.precached_prompt_tokens / base if base else 0.0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
            self.precached_prompt_tokens + other.precached_prompt_tokens,
            self.total_tokens + other.total_tokens,
        )


@dataclass(slots=True)
class FunctionCall:
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class Completion:
    content: str
    finish_reason: str
    model: str
    usage: Usage
    function_call: FunctionCall | None = None
    functions_state_id: str | None = None
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        """GigaChat отказал по тематическим ограничениям."""
        return self.finish_reason == "blacklist"


# --------------------------------------------------------------------------- #
# Клиент
# --------------------------------------------------------------------------- #

class GigaChatClient:
    """
    Один экземпляр = один аккаунт (одна пара ключей).

    max_streams: лимит одновременных запросов.
        физлицо  -> 1
        юрлицо   -> 10 по умолчанию
    Превышение лимита даёт 429; семафор дешевле, чем ретраи.
    """

    def __init__(
        self,
        *,
        credentials: str | None = None,
        scope: str = "GIGACHAT_API_PERS",
        base_url: str = LEGACY_BASE,
        max_streams: int = 1,
        verify: bool | str = False,
        timeout: float = 60.0,
    ) -> None:
        self._credentials = credentials or os.environ["GIGACHAT_CREDENTIALS"]
        self._scope = scope
        self._base = base_url.rstrip("/")
        self._sem = asyncio.Semaphore(max_streams)
        self._http = httpx.AsyncClient(verify=verify, timeout=timeout)
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ----------------------------- OAuth ---------------------------------- #

    async def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        async with self._token_lock:
            if self._token and time.time() < self._token_expires_at - 60:
                return self._token
            resp = await self._http.post(
                OAUTH_URL,
                headers={
                    "Authorization": f"Basic {self._credentials}",
                    "RqUID": str(uuid.uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"scope": self._scope},
            )
            resp.raise_for_status()
            payload = resp.json()
            self._token = payload["access_token"]
            # expires_at приходит в миллисекундах epoch
            self._token_expires_at = float(payload.get("expires_at", 0)) / 1000.0
            return self._token

    # ----------------------------- Chat ----------------------------------- #

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str = "GigaChat-2-Pro",
        session_id: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_tokens: int | None = None,
        repetition_penalty: float | None = None,
        response_format: dict[str, Any] | None = None,
        functions: list[dict[str, Any]] | None = None,
        function_call: Literal["none", "auto"] | dict[str, str] | None = None,
        request_id: str | None = None,
        retries: int = 2,
    ) -> Completion:
        """
        Один вызов /chat/completions.

        session_id — САМОЕ ВАЖНОЕ поле для денег.
        Передавайте один и тот же id на весь диалог пациента: сервер
        переиспользует уже посчитанный префикс и не тарифицирует его
        (см. usage.precached_prompt_tokens).
        """
        body: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            body["temperature"] = temperature
        if top_p is not None:
            body["top_p"] = top_p
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if repetition_penalty is not None:
            body["repetition_penalty"] = repetition_penalty
        if response_format is not None:
            body["response_format"] = response_format
        if functions is not None:
            body["functions"] = functions
        if function_call is not None:
            body["function_call"] = function_call

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {await self._access_token()}",
            "X-Request-ID": request_id or str(uuid.uuid4()),
        }
        if session_id:
            headers["X-Session-ID"] = session_id

        url = f"{self._base}/chat/completions"
        last: Exception | None = None

        async with self._sem:
            for attempt in range(retries + 1):
                started = time.monotonic()
                try:
                    resp = await self._http.post(url, headers=headers, json=body)
                    if resp.status_code == 401 and attempt < retries:
                        self._token = None
                        headers["Authorization"] = f"Bearer {await self._access_token()}"
                        continue
                    resp.raise_for_status()
                    return _parse_completion(
                        resp.json(), int((time.monotonic() - started) * 1000)
                    )
                except httpx.HTTPStatusError as exc:
                    last = GigaResponseError(f"chat status={exc.response.status_code}")
                    if exc.response.status_code not in RETRYABLE_STATUS:
                        raise last from exc
                except httpx.HTTPError as exc:
                    last = GigaTransportError(f"chat transport: {exc}")
                if attempt < retries:
                    await asyncio.sleep(0.25 * (2 ** attempt))

        raise last or GigaResponseError("chat failed")

    # ------------------------ Структурный вывод ---------------------------- #

    async def structured(
        self,
        messages: list[dict[str, Any]],
        schema: type[TModel],
        *,
        model: str = "GigaChat-2-Pro",
        session_id: str | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        repair: bool = True,
    ) -> tuple[TModel, Completion]:
        """
        Вернуть валидированный Pydantic-объект.

        response_format={"type": "json_schema", "schema": ..., "strict": true}
        заменяет собой самописный парсер полей и «JSON repair»-вызов.

        repair=True оставляет ровно одну попытку починки: модель получает
        текст своей ошибки валидации. На практике при strict=true она
        срабатывает редко — но защищает от 422 на краевых схемах.
        """
        rf = {
            "type": "json_schema",
            "schema": json_schema_for(schema),
            "strict": True,
        }
        comp = await self.chat(
            messages,
            model=model,
            session_id=session_id,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=rf,
            function_call="none",  # структурный вывод и функции не смешиваем
        )
        try:
            return schema.model_validate_json(_strip_fence(comp.content)), comp
        except (ValidationError, ValueError) as exc:
            if not repair:
                raise GigaResponseError(f"schema validation failed: {exc}") from exc

        repair_messages = [
            *messages,
            {"role": "assistant", "content": comp.content},
            {
                "role": "user",
                "content": (
                    "Ответ не прошёл валидацию по схеме. "
                    "Верни ТОЛЬКО корректный JSON по схеме, без пояснений."
                ),
            },
        ]
        comp2 = await self.chat(
            repair_messages,
            model=model,
            session_id=session_id,
            temperature=0.0,
            max_tokens=max_tokens,
            response_format=rf,
            function_call="none",
        )
        comp2.usage = comp.usage + comp2.usage
        try:
            return schema.model_validate_json(_strip_fence(comp2.content)), comp2
        except (ValidationError, ValueError) as exc:
            raise GigaResponseError(f"schema validation failed twice: {exc}") from exc

    # ---------------------------- Служебное -------------------------------- #

    async def count_tokens(self, texts: list[str], *, model: str = "GigaChat-2-Pro") -> list[int]:
        """POST /tokens/count — точный подсчёт вместо оценки «символы/4»."""
        resp = await self._http.post(
            f"{self._base}/tokens/count",
            headers={
                "Authorization": f"Bearer {await self._access_token()}",
                "Content-Type": "application/json",
            },
            json={"model": model, "input": texts},
        )
        resp.raise_for_status()
        return [int(item["tokens"]) for item in resp.json()]

    async def embeddings(
        self, texts: list[str], *, model: str = "EmbeddingsGigaR"
    ) -> list[list[float]]:
        resp = await self._http.post(
            f"{self._base}/embeddings",
            headers={
                "Authorization": f"Bearer {await self._access_token()}",
                "Content-Type": "application/json",
            },
            json={"model": model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda d: d["index"])]


# --------------------------------------------------------------------------- #
# Хелперы
# --------------------------------------------------------------------------- #

def _parse_completion(payload: dict[str, Any], latency_ms: int) -> Completion:
    try:
        choice = payload["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError) as exc:
        raise GigaResponseError("malformed chat payload") from exc

    raw_fc = message.get("function_call")
    fc = None
    if raw_fc:
        args = raw_fc.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        fc = FunctionCall(name=raw_fc.get("name", ""), arguments=args or {})

    u = payload.get("usage") or {}
    return Completion(
        content=message.get("content") or "",
        finish_reason=choice.get("finish_reason", "stop"),
        model=payload.get("model", ""),
        usage=Usage(
            prompt_tokens=int(u.get("prompt_tokens", 0)),
            completion_tokens=int(u.get("completion_tokens", 0)),
            precached_prompt_tokens=int(u.get("precached_prompt_tokens", 0)),
            total_tokens=int(u.get("total_tokens", 0)),
        ),
        function_call=fc,
        functions_state_id=message.get("functions_state_id"),
        latency_ms=latency_ms,
        raw=payload,
    )


def _strip_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """
    Pydantic -> JSON Schema в виде, который переваривает GigaChat.

    Инлайним $defs: вложенные модели через $ref местами ломают strict-режим.
    Держите схемы плоскими — это ещё и дешевле по токенам.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs.get(ref.split("/")[-1], {})
                merged = {**inline(target)}
                merged.update({k: v for k, v in node.items() if k != "$ref"})
                return merged
            return {k: inline(v) for k, v in node.items()}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    schema = inline(schema)
    schema.setdefault("additionalProperties", False)
    schema.pop("title", None)
    return schema
