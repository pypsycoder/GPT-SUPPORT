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
import time
import uuid

import httpx

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
            logger.debug("[pool] OAuth response status=%s body=%s", resp.status_code, resp.text)
            resp.raise_for_status()
            data = resp.json()

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

                        print(f"[DEBUG] status={resp.status_code} body={resp.text[:500]}")
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
                    logger.warning(
                        "[pool] attempt %d failed (account=%s): %s",
                        attempt + 1, self.account_id, exc,
                    )
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
    if cert_path and os.path.isfile(cert_path):
        return cert_path
    return False


# ---------------------------------------------------------------------------
# Синглтон — импортируется во всех модулях
# ---------------------------------------------------------------------------

pool = AccountPool()
