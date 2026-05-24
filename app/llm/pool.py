"""
GigaChat Account Pool — управление пулом аккаунтов GigaChat API.

Каждый аккаунт имеет один поток (asyncio.Lock), ротация по пулу.
Аккаунты читаются из переменных окружения: GIGACHAT_KEY_A1, GIGACHAT_KEY_A2, ...

Важно:
- пул выбирает только аккаунт / контур;
- модель (`lite` / `pro` / `max`) выбирается в самом запросе через поле `model`.

GigaChat API:
  1. OAuth: POST https://ngw.devices.sberbank.ru:9443/api/v2/oauth
     Authorization: Basic <api_key>, body: scope=GIGACHAT_API_PERS
  2. Chat: POST https://gigachat.devices.sberbank.ru/api/v1/chat/completions
     Authorization: Bearer <access_token>

NOTE: GigaChat использует российские сертификаты. На dev-сервере `verify=False`.
      В продакшне передайте путь к CA-сертификату через GIGACHAT_CERT_PATH.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid

import httpx

from app.llm.errors import LLMConfigurationError, LLMTransportError

logger = logging.getLogger("gpt-support-llm.pool")

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

MODEL_NAMES: dict[str, str] = {
    "lite": "GigaChat-2",
    "pro":  "GigaChat-2-Pro",
    "max":  "GigaChat-2-Max",
}

DEFAULT_ACCOUNT_GROUP = "freemium_test"
DEFAULT_SCOPE = "GIGACHAT_API_PERS"
_INSECURE_SSL_ENV = "GIGACHAT_ALLOW_INSECURE_SSL"
_REDACTED_TOKEN_PATTERNS = (
    re.compile(r'("access_token"\s*:\s*")[^"]+(")', flags=re.IGNORECASE),
    re.compile(r'("refresh_token"\s*:\s*")[^"]+(")', flags=re.IGNORECASE),
    re.compile(r'("token"\s*:\s*")[^"]+(")', flags=re.IGNORECASE),
)


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_response_excerpt(body: str, *, limit: int = 200) -> str:
    excerpt = " ".join(str(body or "").split())
    if not excerpt:
        return ""

    for pattern in _REDACTED_TOKEN_PATTERNS:
        excerpt = pattern.sub(r"\1<redacted>\2", excerpt)

    if len(excerpt) <= limit:
        return excerpt
    return excerpt[: limit - 3] + "..."


def _normalize_httpx_error(exc: httpx.HTTPError) -> LLMConfigurationError | LLMTransportError:
    message = str(exc)
    lowered = message.lower()
    if "certificate verify failed" in lowered or "self-signed certificate" in lowered:
        return LLMConfigurationError(
            "SSL verification failed for GigaChat. "
            "Set GIGACHAT_CERT_PATH to the provider CA bundle or, for local dev only, "
            "set GIGACHAT_ALLOW_INSECURE_SSL=true."
        )

    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return LLMTransportError(f"GigaChat HTTP {exc.response.status_code}: {exc}")

    return LLMTransportError(f"GigaChat transport error: {exc}")


# ---------------------------------------------------------------------------
# GigaChatClient
# ---------------------------------------------------------------------------

class GigaChatClient:
    """
    Клиент для одного аккаунта GigaChat.

    Ограничение: один параллельный запрос (asyncio.Lock).
    Автоматически обновляет OAuth-токен при истечении.
    """

    def __init__(
        self,
        account_id: str,
        api_key: str,
        *,
        account_group: str = DEFAULT_ACCOUNT_GROUP,
        scope: str = DEFAULT_SCOPE,
    ) -> None:
        self.account_id = account_id
        self.api_key = api_key
        self.account_group = account_group
        self.scope = scope
        self.tokens_used: int = 0

        self._lock = asyncio.Lock()
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def is_busy(self) -> bool:
        """True если клиент сейчас обрабатывает запрос."""
        return self._lock.locked()

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str:
        """Возвращает действующий access_token, при необходимости обновляет."""
        # Если токен ещё не истёк (с запасом 60 сек), используем кэшированный
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        verify = _get_ssl_verify()
        try:
            async with httpx.AsyncClient(verify=verify, timeout=15.0) as client:
                resp = await client.post(
                    GIGACHAT_AUTH_URL,
                    headers={
                        "Authorization": f"Basic {self.api_key}",
                        "RqUID": str(uuid.uuid4()),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"scope": self.scope},
                )
                logger.debug("[pool] OAuth response status=%s account=%s", resp.status_code, self.account_id)
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError:
                    logger.warning(
                        "[pool] OAuth failed account=%s status=%s body=%s",
                        self.account_id,
                        resp.status_code,
                        _safe_response_excerpt(resp.text),
                    )
                    raise
                data = resp.json()
        except httpx.HTTPError as exc:
            raise _normalize_httpx_error(exc) from exc

        self._access_token = data["access_token"]
        # expires_at приходит в миллисекундах
        self._token_expires_at = data.get("expires_at", 0) / 1000.0
        logger.debug("[pool] Токен обновлён, аккаунт=%s", self.account_id)
        return self._access_token

    # ------------------------------------------------------------------
    # API call
    # ------------------------------------------------------------------

    async def call(
        self,
        messages: list[dict],
        system_prompt: str,
        *,
        model_tier: str = "pro",
        temperature: float = 0.7,
    ) -> tuple[str, int, int, int]:
        """
        Отправляет запрос к GigaChat API.

        Args:
            messages: список {"role": "user"|"assistant", "content": str}
            system_prompt: системный промпт (объединяется с messages)

        Returns:
            (response_text, tokens_input, tokens_output, response_time_ms)

        Raises:
            httpx.HTTPError | RuntimeError: при ошибке после retry
        """
        async with self._lock:
            start = time.monotonic()
            token = await self._get_access_token()
            requested_tier = str(model_tier or "pro").lower()
            model_name = MODEL_NAMES.get(requested_tier, MODEL_NAMES["pro"])

            all_messages = [{"role": "system", "content": system_prompt}, *messages]
            payload = {
                "model": model_name,
                "messages": all_messages,
                "temperature": temperature,
                "max_tokens": 512,
            }

            last_exc: Exception | None = None
            for attempt in range(2):
                try:
                    verify = _get_ssl_verify()
                    async with httpx.AsyncClient(verify=verify, timeout=30.0) as http_client:
                        resp = await http_client.post(
                            GIGACHAT_API_URL,
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json",
                            },
                            json=payload,
                        )
                        resp.raise_for_status()
                        data = resp.json()

                    text = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    tokens_in = usage.get("prompt_tokens", 0)
                    tokens_out = usage.get("completion_tokens", 0)
                    elapsed_ms = int((time.monotonic() - start) * 1000)

                    self.tokens_used += tokens_in + tokens_out
                    logger.info(
                        "[pool] account=%s group=%s model=%s in=%d out=%d time=%dms",
                        self.account_id, self.account_group, model_name, tokens_in, tokens_out, elapsed_ms,
                    )
                    return text, tokens_in, tokens_out, elapsed_ms

                except Exception as exc:
                    last_exc = exc
                    if isinstance(exc, httpx.HTTPError):
                        normalized_exc = _normalize_httpx_error(exc)
                    else:
                        normalized_exc = exc

                    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                        logger.warning(
                            "[pool] attempt %d failed (account=%s status=%s): %s | body=%s",
                            attempt + 1,
                            self.account_id,
                            exc.response.status_code,
                            exc,
                            _safe_response_excerpt(exc.response.text),
                        )
                    else:
                        logger.warning(
                            "[pool] attempt %d failed (account=%s): %s",
                            attempt + 1,
                            self.account_id,
                            normalized_exc,
                        )
                    last_exc = normalized_exc
                    if attempt == 0:
                        # На второй попытке — сбросить токен и получить новый
                        self._access_token = None
                        try:
                            token = await self._get_access_token()
                        except Exception:
                            pass

            raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AccountPool
# ---------------------------------------------------------------------------

class AccountPool:
    """
    Пул аккаунтов GigaChat.

    Читает GIGACHAT_KEY_A1, GIGACHAT_KEY_A2, ... из переменных окружения.
    Модель не закрепляется за аккаунтом: она передаётся в `client.call(...)`.
    Аккаунт может принадлежать к группе, например `freemium_test` или `business`.
    """

    def __init__(self) -> None:
        self.clients: list[GigaChatClient] = []
        self._build_pool()

    def _build_pool(self) -> None:
        for i in range(1, 20):
            account_id = f"A{i}"
            key = os.getenv(f"GIGACHAT_KEY_{account_id}")
            if not key:
                continue  # пропускаем пустые, не прерываем
            account_group = os.getenv(f"GIGACHAT_GROUP_{account_id}", DEFAULT_ACCOUNT_GROUP).strip() or DEFAULT_ACCOUNT_GROUP
            scope = os.getenv(f"GIGACHAT_SCOPE_{account_id}", DEFAULT_SCOPE).strip() or DEFAULT_SCOPE

            client = GigaChatClient(
                account_id=account_id,
                api_key=key,
                account_group=account_group,
                scope=scope,
            )
            self.clients.append(client)
            logger.info("[pool] Добавлен аккаунт %s group=%s scope=%s", account_id, account_group, scope)

        if not self.clients:
            logger.warning("[pool] Нет аккаунтов GigaChat! Задайте GIGACHAT_KEY_A1 в .env")

    async def get_available(
        self,
        account_group: str | None = None,
        *,
        strict: bool = False,
    ) -> GigaChatClient:
        """
        Возвращает незанятый клиент из нужной группы аккаунтов.
        Ждёт до 10 секунд, затем возвращает первый доступный клиент.

        Args:
            account_group: группа аккаунтов, например `freemium_test` или `business`

        Raises:
            RuntimeError: если пул пуст
        """
        if not self.clients:
            raise RuntimeError("AccountPool пуст — нет настроенных аккаунтов GigaChat")

        normalized_group = (account_group or "").strip() or None
        candidates = [
            c for c in self.clients
            if normalized_group is None or c.account_group == normalized_group
        ]
        if not candidates and strict:
            raise RuntimeError(
                f"Нет доступного аккаунта GigaChat для требуемой группы: {normalized_group or DEFAULT_ACCOUNT_GROUP}"
            )
        if not candidates:
            candidates = self.clients  # fallback на любой доступный аккаунт

        # Сортируем: сначала незанятые, потом по account_id для стабильности
        candidates.sort(key=lambda c: (c.is_busy, c.account_id))

        # Первый проход: ищем свободный
        for client in candidates:
            if not client.is_busy:
                return client

        # Все заняты — ждём освобождения (таймаут 10 сек)
        try:
            return await asyncio.wait_for(
                self._wait_for_any(candidates),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[pool] Таймаут ожидания клиента group=%s, возвращаем первый",
                normalized_group or "*",
            )
            return candidates[0]

    @staticmethod
    async def _wait_for_any(clients: list[GigaChatClient]) -> GigaChatClient:
        """Опрашивает список клиентов каждые 200 мс до освобождения."""
        while True:
            for client in clients:
                if not client.is_busy:
                    return client
            await asyncio.sleep(0.2)

    def get_stats(self) -> dict:
        """Статус каждого аккаунта: группа, scope, занятость, суммарные токены."""
        return {
            c.account_id: {
                "account_group": c.account_group,
                "scope": c.scope,
                "is_busy": c.is_busy,
                "tokens_used": c.tokens_used,
            }
            for c in self.clients
        }


# ---------------------------------------------------------------------------
# SSL helper
# ---------------------------------------------------------------------------

def _get_ssl_verify() -> bool | str:
    """
    Возвращает параметр verify для httpx.
    По умолчанию False (GigaChat использует российские CA).
    Можно переопределить через GIGACHAT_CERT_PATH=/path/to/ca.pem.
    """
    cert_path = os.getenv("GIGACHAT_CERT_PATH", "").strip()
    if cert_path:
        if os.path.isfile(cert_path):
            return cert_path
        logger.warning("[pool] GIGACHAT_CERT_PATH is set but file not found: %s", cert_path)

    if _env_flag(_INSECURE_SSL_ENV):
        return False

    return True


# ---------------------------------------------------------------------------
# Синглтон — импортируется во всех модулях
# ---------------------------------------------------------------------------

pool = AccountPool()
