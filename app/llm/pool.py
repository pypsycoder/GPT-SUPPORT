"""
GigaChat Account Pool - account selection, token refresh, and provider calls.

Each account handles one concurrent request via asyncio.Lock.
Accounts are read from environment variables: GIGACHAT_KEY_A1, GIGACHAT_KEY_A2, ...
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass

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

    async def call(self, messages: list[dict], system_prompt: str) -> tuple[str, int, int, int]:
        async with self._state.lock:
            start = time.monotonic()
            token = await self._get_access_token()
            model_name = MODEL_NAMES.get(self.model_tier, "GigaChat-2-Pro")

            payload = {
                "model": model_name,
                "messages": [{"role": "system", "content": system_prompt}, *messages],
                "temperature": 0.7,
                "max_tokens": 512,
            }

            last_exc: LLMTransportError | LLMResponseError | None = None
            for attempt in range(2):
                try:
                    data = await request_json_with_policy(
                        "chat",
                        method="POST",
                        url=GIGACHAT_API_URL,
                        operation=f"chat completion for account {self.account_id}",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        json_body=payload,
                    )

                    text = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    tokens_in = usage.get("prompt_tokens", 0)
                    tokens_out = usage.get("completion_tokens", 0)
                    elapsed_ms = int((time.monotonic() - start) * 1000)

                    self.tokens_used += tokens_in + tokens_out
                    logger.info(
                        "[pool] account=%s model=%s in=%d out=%d time=%dms",
                        self.account_id,
                        model_name,
                        tokens_in,
                        tokens_out,
                        elapsed_ms,
                    )
                    return text, tokens_in, tokens_out, elapsed_ms

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
                raise LLMResponseError(
                    f"chat failed for account {self.account_id} without a classified error"
                )
            raise last_exc


class AccountPool:
    _FIXED_TIERS: dict[str, str] = {"A1": "lite", "A2": "pro"}

    def __init__(self) -> None:
        self.clients: list[GigaChatClient] = []
        self._build_pool()

    def _build_pool(self) -> None:
        configured_accounts: list[tuple[str, str, str]] = []
        available_tiers: set[str] = set()

        for i in range(1, 20):
            account_id = f"A{i}"
            key = os.getenv(f"GIGACHAT_KEY_{account_id}")
            if not key:
                continue
            key = _ascii_only(key).strip()
            tier = self._FIXED_TIERS.get(account_id) or os.getenv(
                f"GIGACHAT_MODEL_{account_id}", "pro"
            )
            if tier not in MODEL_NAMES:
                tier = "pro"

            configured_accounts.append((account_id, key, tier))
            self._add_client(account_id=account_id, api_key=key, tier=tier)
            available_tiers.add(tier)

        unique_keys = {key for _, key, _ in configured_accounts}
        if configured_accounts and len(unique_keys) == 1:
            base_account_id, shared_key, _ = configured_accounts[0]
            shared_state = next(
                client._state for client in self.clients
                if client.account_id == base_account_id
            )
            for tier in MODEL_NAMES:
                if tier in available_tiers:
                    continue
                alias_account_id = f"{base_account_id}-{tier}"
                self._add_client(
                    account_id=alias_account_id,
                    api_key=shared_key,
                    tier=tier,
                    shared_state=shared_state,
                )
                logger.info(
                    "[pool] added shared-tier alias %s tier=%s using key from %s",
                    alias_account_id,
                    tier,
                    base_account_id,
                )

        if not self.clients:
            logger.warning("[pool] no GigaChat accounts configured")

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

    async def get_available(self, model_tier: str, *, allow_fallback: bool = False) -> GigaChatClient:
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

    def get_stats(self) -> dict:
        return {
            c.account_id: {
                "tier": c.model_tier,
                "model": MODEL_NAMES.get(c.model_tier, "unknown"),
                "is_busy": c.is_busy,
                "tokens_used": c.tokens_used,
            }
            for c in self.clients
        }


def _ascii_only(s: str) -> str:
    return s.encode("ascii", errors="ignore").decode("ascii")


pool = AccountPool()
