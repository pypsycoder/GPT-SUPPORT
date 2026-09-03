"""
LLM Account Pool - provider selection, account selection, token refresh, calls.

Два провайдера, выбор по ``LLM_PROVIDER`` (``sber`` | ``cloudru``, default
``sber``):

* **sber** — GigaChat API Сбербанка. Каждый ключ ``GIGACHAT_KEY_<id>`` = аккаунт
  со своим ``asyncio.Lock`` (PERS scope = 1 поток/ключ), поднят под все три тира
  через алиасы ``<id>-lite/-pro/-max`` на общем локе.
* **cloudru** — Cloud.ru Evolution Foundation Models, OpenAI-совместимый шлюз.
  Один ключ ``CLOUD_RU_KEY`` (формата ``<keyid>.<secret>``, идёт в Bearer как
  есть — без OAuth), лимит по RPM/TPM аккаунта, не по потокам; конкурентность
  ограничивает ``asyncio.Semaphore(CLOUD_RU_CONCURRENCY)``.

Эмбеддинги (``app/llm/embeddings.py``) ходят ВСЕГДА через Сбер — индекс построен
на модели ``Embeddings``. При ``LLM_PROVIDER=cloudru`` всё равно нужен
``GIGACHAT_KEY_*``; клиенты обоих провайдеров живут в пуле одновременно,
``get_available`` по умолчанию отдаёт активного, но принимает ``provider=``.
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

CLOUDRU_CHAT_URL = "https://foundation-models.api.cloud.ru/v1/chat/completions"
# Флагман Сбера на Cloud.ru (GigaChat 3.5 Ultra) — на safety-бенче recall
# {act,plan} 0.97 против 0.86 у GigaChat-2-Pro. См. ROADMAP_AGENT.md Фаза 6.
CLOUDRU_DEFAULT_MODEL = "ai-sage/GigaChat3.5-432B-A28B"
DEFAULT_CLOUDRU_CONCURRENCY = 8

MODEL_NAMES: dict[str, str] = {
    "lite": "GigaChat-2",
    "pro": "GigaChat-2-Pro",
    "max": "GigaChat-2-Max",
}

_TIER_PRIORITY: dict[str, int] = {"lite": 0, "pro": 1, "max": 2}


@dataclass(frozen=True)
class ProviderSpec:
    """Разъём под конкретный LLM-бэкенд — всё, чем провайдеры отличаются:
    адрес, способ авторизации, имена моделей, серверные заголовки."""

    name: str                 # "sber" | "cloudru"
    chat_url: str
    auth_url: str | None      # None → api_key идёт в Bearer как есть (без OAuth)
    oauth_scope: str
    models: dict[str, str]    # tier -> имя модели у провайдера
    send_session_header: bool  # X-Session-ID (префиксный кэш Сбера)

    def model_for(self, tier: str) -> str:
        return (
            self.models.get(tier)
            or self.models.get("pro")
            or next(iter(self.models.values()))
        )


SBER = ProviderSpec(
    name="sber",
    chat_url=GIGACHAT_API_URL,
    auth_url=GIGACHAT_AUTH_URL,
    oauth_scope="GIGACHAT_API_PERS",
    models=MODEL_NAMES,
    send_session_header=True,
)


def _cloudru_spec() -> ProviderSpec:
    """``ProviderSpec`` для Cloud.ru — имена моделей из окружения.

    ``CLOUD_RU_MODEL`` задаёт модель на все тиры; ``CLOUD_RU_MODEL_<TIER>``
    переопределяет отдельный тир (напр. дешёвый ``lite`` на ``GigaChat3-10B``).
    """
    default = (os.getenv("CLOUD_RU_MODEL") or "").strip() or CLOUDRU_DEFAULT_MODEL
    return ProviderSpec(
        name="cloudru",
        chat_url=CLOUDRU_CHAT_URL,
        auth_url=None,
        oauth_scope="",
        models={
            tier: (os.getenv(f"CLOUD_RU_MODEL_{tier.upper()}") or "").strip() or default
            for tier in MODEL_NAMES
        },
        send_session_header=False,
    )

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
    # Сбер: Lock (1 поток/ключ). Cloud.ru: Semaphore(CLOUD_RU_CONCURRENCY).
    # Обоим хватает `async with` и `.locked()` — вызывающий код не различает.
    lock: asyncio.Lock | asyncio.Semaphore | None = None
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
        provider: ProviderSpec = SBER,
    ) -> None:
        self.account_id = account_id
        self.model_tier = model_tier
        self.provider = provider
        self.tokens_used: int = 0
        self._state = shared_state or _SharedAccountState(api_key=api_key)

    @property
    def is_busy(self) -> bool:
        return self._state.lock.locked()

    async def _get_access_token(self) -> str:
        # Cloud.ru: ключ <keyid>.<secret> и есть Bearer-токен, обмена нет.
        if self.provider.auth_url is None:
            return self._state.api_key

        if self._state.access_token and time.time() < self._state.token_expires_at - 60:
            return self._state.access_token

        async with self._state.token_lock:
            if self._state.access_token and time.time() < self._state.token_expires_at - 60:
                return self._state.access_token

            try:
                data = await request_json_with_policy(
                    "oauth",
                    method="POST",
                    url=self.provider.auth_url,
                    operation=f"oauth for account {self.account_id}",
                    headers={
                        "Authorization": f"Basic {self._state.api_key}",
                        "RqUID": str(uuid.uuid4()),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"scope": self.provider.oauth_scope},
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
            model_name = self.provider.model_for(self.model_tier)

            last_exc: LLMTransportError | LLMResponseError | None = None
            for attempt in range(2):
                try:
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    }
                    if session_id and self.provider.send_session_header:
                        headers["X-Session-ID"] = session_id

                    data = await request_json_with_policy(
                        "chat",
                        method="POST",
                        url=self.provider.chat_url,
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
                    # Сбер: precached_prompt_tokens (плоско). Cloud.ru (OpenAI-совм.):
                    # prompt_tokens_details.cached_tokens.
                    precached_tokens = (
                        usage.get("precached_prompt_tokens")
                        or (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                        or 0
                    )
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
            "model": self.provider.model_for(self.model_tier),
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
            "model": self.provider.model_for(self.model_tier),
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

        ``response_format`` с JSON-схемой (форма зависит от провайдера, см.
        ``structured.response_format_for``) заменяет самописный парсер полей:
        модель физически не может вернуть карточку без обязательного поля.

        ``repair=True`` оставляет ровно одну попытку починки — модель получает
        текст своей ошибки валидации. При ``strict: true`` срабатывает редко,
        но защищает от краевых схем. Repair-вызов уходит в телеметрию со своим
        ``step`` (``<step>_repair``), чтобы его долю можно было посчитать SQL-ом.
        """
        response_format = structured.response_format_for(
            schema, provider=self.provider.name
        )

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
    """Пул LLM-клиентов обоих провайдеров.

    **Сбер:** каждый ключ ``GIGACHAT_KEY_<id>`` = аккаунт со своим
    ``_SharedAccountState`` (→ свой ``asyncio.Lock``, +1 к конкурентности),
    поднят под все три тира; алиасы ``<id>-lite/-pro/-max`` делят один лок, но
    у GigaChat это раздельные серверные префикс-кэши (pipeline/STRUCTURE.md §7).
    ``GIGACHAT_MODEL_<id>`` (``lite``|``pro``|``max``) пришпиливает аккаунт к
    одному тиру (``account_id`` тогда без суффикса).

    **Cloud.ru:** один ключ ``CLOUD_RU_KEY``, клиенты ``cloudru-lite/-pro/-max``
    на общем ``asyncio.Semaphore(CLOUD_RU_CONCURRENCY)``.

    ``LLM_PROVIDER`` (``sber`` default | ``cloudru``) — кого отдаёт
    ``get_available`` по умолчанию. Клиенты обоих провайдеров строятся всегда
    (если заданы ключи): ``embeddings.py`` явно просит ``provider="sber"``.
    """

    _KEY_PREFIX = "GIGACHAT_KEY_"
    _VALID_PROVIDERS = ("sber", "cloudru")

    def __init__(self) -> None:
        self.clients: list[GigaChatClient] = []
        raw = (os.getenv("LLM_PROVIDER") or "sber").strip().lower()
        if raw not in self._VALID_PROVIDERS:
            logger.warning("[pool] LLM_PROVIDER=%r не распознан → 'sber'", raw)
            raw = "sber"
        # _env_provider — из окружения (дефолт при пустой БД-настройке).
        # _chat_provider — эффективный: его меняет set_active_provider()
        # (переключатель в researcher-панели, значение в public.app_settings).
        self._env_provider = raw
        self._chat_provider = raw
        try:
            self._cloudru_concurrency = max(
                1, int(os.getenv("CLOUD_RU_CONCURRENCY") or DEFAULT_CLOUDRU_CONCURRENCY)
            )
        except ValueError:
            self._cloudru_concurrency = DEFAULT_CLOUDRU_CONCURRENCY
        self._build_pool()

    @property
    def chat_provider(self) -> str:
        return self._chat_provider

    @property
    def env_provider(self) -> str:
        return self._env_provider

    def configured_providers(self) -> list[str]:
        """Провайдеры, под которые реально есть клиенты (заданы ключи)."""
        return sorted({c.provider.name for c in self.clients})

    def set_active_provider(self, name: str) -> bool:
        """Переключить активного провайдера чата в рантайме (без пересборки —
        клиенты обоих провайдеров уже в пуле). Возвращает True, если сменилось.

        Отклоняет провайдера, под которого нет клиентов (не задан ключ).
        """
        name = (name or "").strip().lower()
        if name not in self._VALID_PROVIDERS:
            raise ValueError(f"неизвестный провайдер: {name!r}")
        if name not in self.configured_providers():
            raise LLMConfigurationError(
                f"провайдер '{name}' не настроен — нет ключа "
                f"({'CLOUD_RU_KEY' if name == 'cloudru' else 'GIGACHAT_KEY_*'})"
            )
        if name == self._chat_provider:
            return False
        logger.info("[pool] активный провайдер чата %s → %s", self._chat_provider, name)
        self._chat_provider = name
        return True

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
        self._build_sber_clients()
        self._build_cloudru_clients()
        if not self.clients:
            logger.warning(
                "[pool] нет ни одного LLM-аккаунта (ни GIGACHAT_KEY_*, ни CLOUD_RU_KEY)"
            )
            return
        logger.info(
            "[pool] чат-провайдер=%s; клиентов: sber=%d cloudru=%d",
            self._chat_provider,
            sum(c.provider.name == "sber" for c in self.clients),
            sum(c.provider.name == "cloudru" for c in self.clients),
        )

    def _build_sber_clients(self) -> None:
        for account_id, key in self._discover_accounts():
            forced = os.getenv(f"GIGACHAT_MODEL_{account_id}", "").strip().lower()
            tiers = [forced] if forced in MODEL_NAMES else list(MODEL_NAMES)
            shared_state = _SharedAccountState(api_key=key)
            for tier in tiers:
                alias = account_id if len(tiers) == 1 else f"{account_id}-{tier}"
                self._add_client(
                    account_id=alias, api_key=key, tier=tier,
                    shared_state=shared_state, provider=SBER,
                )

    def _build_cloudru_clients(self) -> None:
        key = _ascii_only(os.getenv("CLOUD_RU_KEY") or "").strip()
        if not key:
            if self._chat_provider == "cloudru":
                logger.warning(
                    "[pool] LLM_PROVIDER=cloudru, но CLOUD_RU_KEY не задан — чат не поедет"
                )
            return
        spec = _cloudru_spec()
        shared_state = _SharedAccountState(
            api_key=key, lock=asyncio.Semaphore(self._cloudru_concurrency)
        )
        for tier in MODEL_NAMES:
            self._add_client(
                account_id=f"cloudru-{tier}", api_key=key, tier=tier,
                shared_state=shared_state, provider=spec,
            )

    def _add_client(
        self,
        *,
        account_id: str,
        api_key: str,
        tier: str,
        shared_state: _SharedAccountState | None = None,
        provider: ProviderSpec = SBER,
    ) -> None:
        client = GigaChatClient(
            account_id=account_id,
            api_key=api_key,
            model_tier=tier,
            shared_state=shared_state,
            provider=provider,
        )
        self.clients.append(client)
        logger.info("[pool] + %s (%s, tier=%s)", account_id, provider.name, tier)

    async def get_available(
        self,
        model_tier: str,
        *,
        allow_fallback: bool = False,
        sticky_key: str | None = None,
        provider: str | None = None,
    ) -> GigaChatClient:
        """Клиент под тир. ``provider`` (``sber``|``cloudru``) переопределяет
        активного из ``LLM_PROVIDER`` — ``embeddings.py`` так фиксирует Сбер.
        """
        if not self.clients:
            raise LLMConfigurationError("No LLM accounts configured")

        want = provider or self._chat_provider
        scoped = [c for c in self.clients if c.provider.name == want]
        if not scoped:
            if provider is not None:
                raise LLMConfigurationError(f"No '{provider}' LLM account configured")
            # у активного провайдера нет клиентов — отдаём что есть
            scoped = self.clients

        tier = model_tier.lower()
        min_priority = _TIER_PRIORITY.get(tier, 1)
        candidates = [
            c for c in scoped
            if _TIER_PRIORITY.get(c.model_tier, 1) >= min_priority
        ]
        if not candidates and not allow_fallback:
            raise LLMConfigurationError(
                f"No LLM account configured for requested tier '{tier}'"
            )
        if not candidates:
            candidates = scoped

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
        """Уникальных локов активного чат-провайдера = потолок конкурентности."""
        return len({
            id(c._state) for c in self.clients
            if c.provider.name == self._chat_provider
        })

    @property
    def proactive_concurrency(self) -> int:
        """Сколько пациентов проактивный планировщик обрабатывает разом.

        Сбер: число ключей (1 поток/ключ). Cloud.ru: ``CLOUD_RU_CONCURRENCY``
        (лимит по RPM/TPM аккаунта, не по потокам).
        """
        if self._chat_provider == "cloudru":
            return self._cloudru_concurrency
        return max(1, self.account_count)

    def get_stats(self) -> dict:
        return {
            c.account_id: {
                "provider": c.provider.name,
                "model_tier": c.model_tier,
                "model": c.provider.model_for(c.model_tier),
                "is_busy": c.is_busy,
                "tokens_used": c.tokens_used,
            }
            for c in self.clients
        }


def _ascii_only(s: str) -> str:
    return s.encode("ascii", errors="ignore").decode("ascii")


pool = AccountPool()
