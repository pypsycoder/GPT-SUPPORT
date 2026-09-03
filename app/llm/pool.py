"""
GigaChat Account Pool - account selection, token refresh, and provider calls.

Each account handles one concurrent request via asyncio.Lock, so N configured
keys == N concurrent GigaChat streams (PERS scope = 1 stream/key server-side).
Accounts are read from any ``GIGACHAT_KEY_<id>`` env var (``GIGACHAT_KEY_A1``,
``GIGACHAT_KEY_L1``, ...); each account serves all three tiers (lite/pro/max)
via ``<id>-lite/-pro/-max`` aliases that share the account's single lock.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.llm import structured, telemetry
from app.llm.errors import LLMConfigurationError, LLMResponseError, LLMTransportError
from app.llm.http import request_json_with_policy

logger = logging.getLogger("gpt-support-llm.pool")

GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

MODEL_NAMES: dict[str, str] = {
    "lite": "GigaChat-2",
    "pro": "GigaChat-2-Pro",
    "max": "GigaChat-2-Max",
}

_TIER_PRIORITY: dict[str, int] = {"lite": 0, "pro": 1, "max": 2}

# JSON дороже плоского текста на скобки и ключи — потолок в 512 токенов,
# рассчитанный на карточку «поле: значение», обрезал бы длинные ответы
# education-эксперта на середине и ломал бы валидацию схемы.
_STRUCTURED_MAX_TOKENS = 900

_STRUCTURED_REPAIR_PROMPT = (
    "Ответ не прошёл валидацию по схеме. "
    "Верни ТОЛЬКО корректный JSON по схеме, без пояснений и без markdown."
)


@dataclass(slots=True)
class StructuredResult:
    """Результат ``GigaChatClient.structured()``."""

    parsed: Any
    raw_text: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    repair_attempts: int = 0
    # Ошибка первой попытки, которую вылечила починка. Без неё удачный ход
    # выглядит бесплатным, и схему, которая стабильно не проходит с первого
    # раза, нечем отличить от схемы, которая проходит.
    first_error: str | None = None


@dataclass(slots=True)
class FunctionCall:
    """Запрос модели на вызов инструмента (``message.function_call``)."""

    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class FunctionCallResult:
    """Результат ``GigaChatClient.call_with_functions()``."""

    content: str
    function_call: FunctionCall | None
    functions_state_id: str | None
    finish_reason: str | None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0


@dataclass(slots=True)
class _RawCompletion:
    """Сырой разобранный ответ ``/chat/completions`` — общий для ``call()`` и
    ``call_with_functions()``. Дальнейший разбор (текст vs function_call)
    остаётся за вызывающей стороной."""

    message: dict[str, Any]
    tokens_in: int
    tokens_out: int
    latency_ms: int
    finish_reason: str | None


def error_preview(text: str, limit: int = 400) -> str:
    """Сырой ответ модели в одну строку — чтобы попадал в текст ошибки."""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def session_key(patient_id: int, thread_id: str) -> str:
    """Стабильный ключ треда для заголовка X-Session-ID и sticky-роутинга аккаунтов.

    Не должен содержать ничего идентифицирующего пациента, кроме
    внутреннего числового id (уходит на сервер Сбера и логируется там).
    """
    return f"p{patient_id}-{thread_id}"


def _stable_index(key: str, modulo: int) -> int:
    """Детерминированный индекс по ключу, устойчивый к перезапуску процесса.

    Встроенный ``hash()`` для строк солится PYTHONHASHSEED и меняется
    между рестартами — для sticky-роутинга это недопустимо.
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulo


@dataclass
class _SharedAccountState:
    api_key: str
    access_token: str | None = None
    token_expires_at: float = 0.0
    lock: asyncio.Lock | None = None
    token_lock: asyncio.Lock | None = None

    def __post_init__(self) -> None:
        if self.lock is None:
            self.lock = asyncio.Lock()
        if self.token_lock is None:
            self.token_lock = asyncio.Lock()


class GigaChatClient:
    def __init__(
        self,
        account_id: str,
        api_key: str,
        model_tier: str,
        *,
        shared_state: _SharedAccountState | None = None,
    ) -> None:
        self.account_id = account_id
        self.model_tier = model_tier
        self.tokens_used: int = 0
        self._state = shared_state or _SharedAccountState(api_key=api_key)

    @property
    def is_busy(self) -> bool:
        return self._state.lock.locked()

    async def _get_access_token(self) -> str:
        if self._state.access_token and time.time() < self._state.token_expires_at - 60:
            return self._state.access_token

        async with self._state.token_lock:
            if self._state.access_token and time.time() < self._state.token_expires_at - 60:
                return self._state.access_token

            try:
                data = await request_json_with_policy(
                    "oauth",
                    method="POST",
                    url=GIGACHAT_AUTH_URL,
                    operation=f"oauth for account {self.account_id}",
                    headers={
                        "Authorization": f"Basic {self._state.api_key}",
                        "RqUID": str(uuid.uuid4()),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"scope": "GIGACHAT_API_PERS"},
                )
                access_token = _ascii_only(data["access_token"])
                expires_at = data.get("expires_at", 0) / 1000.0
            except (KeyError, TypeError, ValueError) as exc:
                raise LLMResponseError(
                    f"oauth returned invalid payload for account {self.account_id}"
                ) from exc

            self._state.access_token = access_token
            self._state.token_expires_at = expires_at
            logger.debug("[pool] token refreshed account=%s", self.account_id)
            return self._state.access_token

    async def _execute(
        self,
        payload: dict[str, Any],
        *,
        step: str | None,
        patient_id: int | None,
        session_id: str | None,
        prefix_fp: str | None,
    ) -> _RawCompletion:
        """``POST /chat/completions`` с ретраем на протухший токен и телеметрией.

        Общая обвязка для ``call()`` и ``call_with_functions()`` (шаг 7):
        транспорт, ретраи, логирование — идентичны для обоих путей. Разбор
        полей ответа (текст vs ``function_call``) остаётся за вызывающей
        стороной, поэтому здесь наружу отдаётся весь ``message`` целиком.

        Извлечение ``message`` тоже внутри retry-блока: малформед-ответ
        (``choices`` пуст/не тот тип) получает ту же повторную попытку, что и
        раньше в недифференцированном ``call()``.
        """
        async with self._state.lock:
            start = time.monotonic()
            token = await self._get_access_token()
            model_name = MODEL_NAMES.get(self.model_tier, MODEL_NAMES["pro"])

            last_exc: LLMTransportError | LLMResponseError | None = None
            for attempt in range(2):
                try:
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    }
                    if session_id:
                        headers["X-Session-ID"] = session_id

                    data = await request_json_with_policy(
                        "chat",
                        method="POST",
                        url=GIGACHAT_API_URL,
                        operation=f"chat completion for account {self.account_id}",
                        headers=headers,
                        json_body=payload,
                    )

                    message = data["choices"][0]["message"]
                    if not isinstance(message, dict):
                        raise TypeError("message is not a dict")
                    usage = data.get("usage", {})
                    tokens_in = usage.get("prompt_tokens", 0)
                    tokens_out = usage.get("completion_tokens", 0)
                    precached_tokens = usage.get("precached_prompt_tokens", 0)
                    total_tokens = usage.get("total_tokens", tokens_in + tokens_out)
                    finish_reason = data["choices"][0].get("finish_reason")
                    elapsed_ms = int((time.monotonic() - start) * 1000)

                    self.tokens_used += tokens_in + tokens_out
                    logger.info(
                        "[pool] account=%s model=%s in=%d out=%d precached=%d time=%dms",
                        self.account_id,
                        model_name,
                        tokens_in,
                        tokens_out,
                        precached_tokens,
                        elapsed_ms,
                    )
                    asyncio.create_task(
                        telemetry.log_call(
                            account_id=self.account_id,
                            model=model_name,
                            step=step,
                            patient_id=patient_id,
                            session_key=session_id,
                            prefix_fp=prefix_fp,
                            prompt_tokens=tokens_in,
                            completion_tokens=tokens_out,
                            precached_tokens=precached_tokens,
                            total_tokens=total_tokens,
                            latency_ms=elapsed_ms,
                            finish_reason=finish_reason,
                            ok=True,
                        )
                    )
                    return _RawCompletion(
                        message=message,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        latency_ms=elapsed_ms,
                        finish_reason=finish_reason,
                    )

                except (LLMTransportError, LLMResponseError) as exc:
                    last_exc = exc
                    logger.warning(
                        "[pool] attempt %d provider error (account=%s): %s",
                        attempt + 1,
                        self.account_id,
                        exc,
                    )
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    last_exc = LLMResponseError(
                        f"chat returned invalid payload for account {self.account_id}"
                    )
                    logger.warning(
                        "[pool] attempt %d invalid payload (account=%s): %s",
                        attempt + 1,
                        self.account_id,
                        exc,
                    )

                if attempt == 0:
                    self._state.access_token = None
                    try:
                        token = await self._get_access_token()
                    except (LLMTransportError, LLMResponseError):
                        logger.warning(
                            "[pool] token refresh failed after attempt %d (account=%s)",
                            attempt + 1,
                            self.account_id,
                        )

            if last_exc is None:
                last_exc = LLMResponseError(
                    f"chat failed for account {self.account_id} without a classified error"
                )
            asyncio.create_task(
                telemetry.log_call(
                    account_id=self.account_id,
                    model=model_name,
                    step=step,
                    patient_id=patient_id,
                    session_key=session_id,
                    prefix_fp=prefix_fp,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    ok=False,
                    error=str(last_exc)[:500],
                )
            )
            raise last_exc

    async def call(
        self,
        messages: list[dict],
        system_prompt: str,
        *,
        temperature: float = 0.7,
        step: str | None = None,
        patient_id: int | None = None,
        session_id: str | None = None,
        prefix_fp: str | None = None,
        response_format: dict | None = None,
        max_tokens: int = 512,
    ) -> tuple[str, int, int, int]:
        payload: dict[str, Any] = {
            "model": MODEL_NAMES.get(self.model_tier, MODEL_NAMES["pro"]),
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            # functions в этом запросе не передаём: смешивать их с
            # response_format нельзя, поведение непредсказуемо.
            payload["response_format"] = response_format

        raw = await self._execute(
            payload, step=step, patient_id=patient_id, session_id=session_id, prefix_fp=prefix_fp
        )
        text = raw.message.get("content") or ""
        return text, raw.tokens_in, raw.tokens_out, raw.latency_ms

    async def call_with_functions(
        self,
        messages: list[dict],
        system_prompt: str,
        *,
        functions: list[dict[str, Any]],
        function_call: str | dict[str, str] = "auto",
        temperature: float = 0.3,
        step: str | None = None,
        patient_id: int | None = None,
        session_id: str | None = None,
        prefix_fp: str | None = None,
        max_tokens: int = 512,
    ) -> FunctionCallResult:
        """Нативный tool-calling (шаг 7). ``response_format`` здесь не передаётся
        никогда — смешивать functions и структурный вывод нельзя (см. ``call()``).
        """
        payload: dict[str, Any] = {
            "model": MODEL_NAMES.get(self.model_tier, MODEL_NAMES["pro"]),
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if functions:
            payload["functions"] = functions
            payload["function_call"] = function_call or "auto"

        raw = await self._execute(
            payload, step=step, patient_id=patient_id, session_id=session_id, prefix_fp=prefix_fp
        )

        fc: FunctionCall | None = None
        raw_fc = raw.message.get("function_call")
        if raw_fc:
            args = raw_fc.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            fc = FunctionCall(name=str(raw_fc.get("name") or ""), arguments=args or {})

        return FunctionCallResult(
            content=raw.message.get("content") or "",
            function_call=fc,
            functions_state_id=raw.message.get("functions_state_id"),
            finish_reason=raw.finish_reason,
            tokens_in=raw.tokens_in,
            tokens_out=raw.tokens_out,
            latency_ms=raw.latency_ms,
        )

    async def structured(
        self,
        messages: list[dict],
        system_prompt: str,
        schema: type[BaseModel],
        *,
        temperature: float = 0.1,
        step: str | None = None,
        patient_id: int | None = None,
        session_id: str | None = None,
        prefix_fp: str | None = None,
        max_tokens: int = _STRUCTURED_MAX_TOKENS,
        repair: bool = True,
    ) -> StructuredResult:
        """Вернуть валидированный Pydantic-объект вместо сырого текста.

        ``response_format={"type": "json_schema", "schema": ..., "strict": true}``
        заменяет самописный парсер полей: модель физически не может вернуть
        карточку без обязательного поля.

        ``repair=True`` оставляет ровно одну попытку починки — модель получает
        текст своей ошибки валидации. При ``strict: true`` срабатывает редко,
        но защищает от краевых схем. Repair-вызов уходит в телеметрию со своим
        ``step`` (``<step>_repair``), чтобы его долю можно было посчитать SQL-ом.
        """
        response_format = structured.response_format_for(schema)

        text, tokens_in, tokens_out, latency_ms = await self.call(
            messages,
            system_prompt,
            temperature=temperature,
            step=step,
            patient_id=patient_id,
            session_id=session_id,
            prefix_fp=prefix_fp,
            response_format=response_format,
            max_tokens=max_tokens,
        )

        try:
            parsed = schema.model_validate_json(structured.strip_fence(text))
            return StructuredResult(
                parsed=parsed,
                raw_text=text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )
        except (ValidationError, ValueError) as exc:
            if not repair:
                raise LLMResponseError(
                    f"schema validation failed: {exc} | raw={error_preview(text)}"
                ) from exc
            first_error = exc

        logger.warning(
            "[pool] structured repair account=%s schema=%s: %s",
            self.account_id,
            schema.__name__,
            first_error,
        )
        repair_messages = [
            *messages,
            {"role": "assistant", "content": text},
            {"role": "user", "content": _STRUCTURED_REPAIR_PROMPT},
        ]
        text2, tokens_in2, tokens_out2, latency_ms2 = await self.call(
            repair_messages,
            system_prompt,
            temperature=0.0,
            step=f"{step}_repair" if step else "structured_repair",
            patient_id=patient_id,
            session_id=session_id,
            prefix_fp=prefix_fp,
            response_format=response_format,
            max_tokens=max_tokens,
        )
        try:
            parsed = schema.model_validate_json(structured.strip_fence(text2))
        except (ValidationError, ValueError) as exc:
            raise LLMResponseError(
                f"schema validation failed twice: {exc} | raw={error_preview(text2)} "
                f"| first={first_error} | first_raw={error_preview(text)}"
            ) from exc

        return StructuredResult(
            parsed=parsed,
            raw_text=text2,
            first_error=f"{first_error} | raw={error_preview(text)}",
            tokens_in=tokens_in + tokens_in2,
            tokens_out=tokens_out + tokens_out2,
            latency_ms=latency_ms + latency_ms2,
            repair_attempts=1,
        )


class AccountPool:
    """Пул GigaChat-аккаунтов.

    Каждый ключ ``GIGACHAT_KEY_<id>`` = один аккаунт со своим
    ``_SharedAccountState`` (→ свой ``asyncio.Lock``, +1 к общей
    конкурентности). Каждый аккаунт поднимается под все три тира; алиасы
    ``<id>-lite/-pro/-max`` делят один лок аккаунта, но у GigaChat это
    раздельные серверные префикс-кэши (см. pipeline/STRUCTURE.md §7).

    ``GIGACHAT_MODEL_<id>`` (``lite`` | ``pro`` | ``max``) — необязательный
    ограничитель: аккаунт поднимается только под один тир (напр. выделенный
    дешёвый аккаунт), и его ``account_id`` остаётся без тир-суффикса.
    """

    _KEY_PREFIX = "GIGACHAT_KEY_"

    def __init__(self) -> None:
        self.clients: list[GigaChatClient] = []
        self._build_pool()

    def _discover_accounts(self) -> list[tuple[str, str]]:
        """``[(account_id, api_key), ...]`` из окружения.

        Дедуп по значению ключа: один кредентиал под двумя именами — один
        аккаунт (иначе два лока молотили бы один серверный лимит → 429).
        Порядок детерминированный по ``account_id`` — ``_stable_index``
        (sticky-роутинг) завязан на стабильный порядок пула между рестартами.
        """
        first_name_for_key: dict[str, str] = {}
        for name, raw in os.environ.items():
            if not name.startswith(self._KEY_PREFIX):
                continue
            account_id = name[len(self._KEY_PREFIX):].strip()
            key = _ascii_only(raw or "").strip()
            if not account_id or not key:
                continue
            first_name_for_key.setdefault(key, account_id)
        return sorted(
            ((account_id, key) for key, account_id in first_name_for_key.items()),
            key=lambda pair: pair[0],
        )

    def _build_pool(self) -> None:
        accounts = self._discover_accounts()
        if not accounts:
            logger.warning("[pool] no GigaChat accounts configured")
            return

        for account_id, key in accounts:
            forced = os.getenv(f"GIGACHAT_MODEL_{account_id}", "").strip().lower()
            tiers = [forced] if forced in MODEL_NAMES else list(MODEL_NAMES)
            shared_state = _SharedAccountState(api_key=key)
            for tier in tiers:
                alias = account_id if len(tiers) == 1 else f"{account_id}-{tier}"
                self._add_client(
                    account_id=alias,
                    api_key=key,
                    tier=tier,
                    shared_state=shared_state,
                )

        logger.info(
            "[pool] %d account(s), %d client(s); per-account concurrency=1",
            len(accounts),
            len(self.clients),
        )

    def _add_client(
        self,
        *,
        account_id: str,
        api_key: str,
        tier: str,
        shared_state: _SharedAccountState | None = None,
    ) -> None:
        client = GigaChatClient(
            account_id=account_id,
            api_key=api_key,
            model_tier=tier,
            shared_state=shared_state,
        )
        self.clients.append(client)
        logger.info("[pool] added account %s tier=%s", account_id, tier)

    async def get_available(
        self,
        model_tier: str,
        *,
        allow_fallback: bool = False,
        sticky_key: str | None = None,
    ) -> GigaChatClient:
        if not self.clients:
            raise LLMConfigurationError("No GigaChat accounts configured")

        tier = model_tier.lower()
        min_priority = _TIER_PRIORITY.get(tier, 1)
        candidates = [
            c for c in self.clients
            if _TIER_PRIORITY.get(c.model_tier, 1) >= min_priority
        ]
        if not candidates and not allow_fallback:
            raise LLMConfigurationError(
                f"No GigaChat account configured for requested tier '{tier}'"
            )
        if not candidates:
            candidates = self.clients

        if sticky_key:
            # Кэш GigaChat живёт в контуре аккаунта — один тред должен всегда
            # попадать на один и тот же аккаунт. Переключение на другой
            # аккаунт из пула происходит только при отказе (см. GigaChatClient.call:
            # ретраи внутри аккаунта, а не переход на другой клиент).
            #
            # `candidates` here includes higher tiers too (priority >= min_priority,
            # e.g. "lite" matches lite/pro/max) — that's fine for the non-sticky
            # least-busy path below, which only upgrades tier when the cheap one is
            # busy. For sticky routing there's no such fallback signal, so we must
            # prefer an exact tier match first, otherwise a "lite" thread could get
            # permanently pinned to a "max" account by hash alone.
            exact_tier_candidates = [c for c in candidates if c.model_tier == tier]
            sticky_pool = exact_tier_candidates or candidates
            return sticky_pool[_stable_index(sticky_key, len(sticky_pool))]

        candidates.sort(key=lambda c: (c.is_busy, _TIER_PRIORITY.get(c.model_tier, 1)))

        for client in candidates:
            if not client.is_busy:
                return client

        try:
            return await asyncio.wait_for(self._wait_for_any(candidates), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("[pool] wait timeout for tier=%s, returning first candidate", tier)
            return candidates[0]

    @staticmethod
    async def _wait_for_any(clients: list[GigaChatClient]) -> GigaChatClient:
        while True:
            for client in clients:
                if not client.is_busy:
                    return client
            await asyncio.sleep(0.2)

    @property
    def account_count(self) -> int:
        """Число физических аккаунтов (уникальных локов) = потолок конкурентности."""
        return len({id(c._state) for c in self.clients})

    def get_stats(self) -> dict:
        return {
            c.account_id: {
                "model_tier": c.model_tier,
                "is_busy": c.is_busy,
                "tokens_used": c.tokens_used,
            }
            for c in self.clients
        }


def _ascii_only(s: str) -> str:
    return s.encode("ascii", errors="ignore").decode("ascii")


pool = AccountPool()
