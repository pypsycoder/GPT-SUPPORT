"""
GigaChat Account Pool — управление пулом аккаунтов GigaChat API.

Каждый аккаунт имеет один поток (asyncio.Lock), ротация по пулу.
Аккаунты читаются из переменных окружения: GIGACHAT_KEY_A1, GIGACHAT_KEY_A2, ...

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

# Порядок tier для fallback (lite → pro → max)
_TIER_PRIORITY: dict[str, int] = {"lite": 0, "pro": 1, "max": 2}


# ---------------------------------------------------------------------------
# GigaChatClient
# ---------------------------------------------------------------------------

class GigaChatClient:
    """
    Клиент для одного аккаунта GigaChat.

    Ограничение: один параллельный запрос (asyncio.Lock).
    Автоматически обновляет OAuth-токен при истечении.
    """

    def __init__(self, account_id: str, api_key: str, model_tier: str) -> None:
        self.account_id = account_id
        self.api_key = api_key
        self.model_tier = model_tier  # "lite" | "pro" | "max"
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
                data={"scope": "GIGACHAT_API_PERS"},
            )
            logger.debug("[pool] OAuth response status=%s body=%s", resp.status_code, resp.text)
            resp.raise_for_status()
            data = resp.json()

        self._access_token = _ascii_only(data["access_token"])
        # expires_at приходит в миллисекундах
        self._token_expires_at = data.get("expires_at", 0) / 1000.0
        logger.debug("[pool] Токен обновлён, аккаунт=%s", self.account_id)
        return self._access_token

    # ------------------------------------------------------------------
    # API call
    # ------------------------------------------------------------------

    async def call(self, messages: list[dict], system_prompt: str) -> tuple[str, int, int, int]:
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
            model_name = MODEL_NAMES.get(self.model_tier, "GigaChat-2-Pro")

            all_messages = [{"role": "system", "content": system_prompt}, *messages]
            payload = {
                "model": model_name,
                "messages": all_messages,
                "temperature": 0.7,
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
                        "[pool] account=%s model=%s in=%d out=%d time=%dms",
                        self.account_id, model_name, tokens_in, tokens_out, elapsed_ms,
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
    A1 → lite, A2 → pro; остальные: GIGACHAT_MODEL_A3 (или "pro" по умолчанию).
    """

    _FIXED_TIERS: dict[str, str] = {"A1": "lite", "A2": "pro"}

    def __init__(self) -> None:
        self.clients: list[GigaChatClient] = []
        self._build_pool()

    def _build_pool(self) -> None:
        for i in range(1, 20):
            account_id = f"A{i}"
            key = os.getenv(f"GIGACHAT_KEY_{account_id}")
            if not key:
                continue  # пропускаем пустые, не прерываем
            key = _ascii_only(key).strip()
            tier = self._FIXED_TIERS.get(account_id) or os.getenv(
                f"GIGACHAT_MODEL_{account_id}", "pro"
            )
            if tier not in MODEL_NAMES:
                tier = "pro"

            client = GigaChatClient(account_id=account_id, api_key=key, model_tier=tier)
            self.clients.append(client)
            logger.info("[pool] Добавлен аккаунт %s tier=%s", account_id, tier)

        if not self.clients:
            logger.warning("[pool] Нет аккаунтов GigaChat! Задайте GIGACHAT_KEY_A1 в .env")

    async def get_available(self, model_tier: str) -> GigaChatClient:
        """
        Возвращает незанятый клиент нужного tier (или выше).
        Ждёт до 10 секунд, затем возвращает первый доступный клиент.

        Args:
            model_tier: "lite" | "pro" | "max"

        Raises:
            RuntimeError: если пул пуст
        """
        if not self.clients:
            raise RuntimeError("AccountPool пуст — нет настроенных аккаунтов GigaChat")

        tier = model_tier.lower()
        min_priority = _TIER_PRIORITY.get(tier, 1)

        # Кандидаты: клиенты с tier >= запрошенного
        candidates = [
            c for c in self.clients
            if _TIER_PRIORITY.get(c.model_tier, 1) >= min_priority
        ]
        if not candidates:
            candidates = self.clients  # fallback на любой

        # Сортируем: сначала незанятые, потом по приоритету tier
        candidates.sort(key=lambda c: (c.is_busy, _TIER_PRIORITY.get(c.model_tier, 1)))

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
            logger.warning("[pool] Таймаут ожидания клиента tier=%s, возвращаем первый", tier)
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
        """Статус каждого аккаунта: tier, занятость, суммарные токены."""
        return {
            c.account_id: {
                "tier": c.model_tier,
                "model": MODEL_NAMES.get(c.model_tier, "unknown"),
                "is_busy": c.is_busy,
                "tokens_used": c.tokens_used,
            }
            for c in self.clients
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ascii_only(s: str) -> str:
    """Удаляет все не-ASCII символы из строки.

    Нужно для заголовков httpx — они должны содержать только ASCII.
    Защищает от UnicodeEncodeError если в env-переменную или ответ API
    попал символ вроде → (\u2192).
    """
    return s.encode("ascii", errors="ignore").decode("ascii")


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
