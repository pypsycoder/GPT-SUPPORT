from __future__ import annotations

import asyncio
import logging
import os

import httpx

from app.llm.errors import LLMResponseError, LLMTransportError


logger = logging.getLogger("gpt-support-llm.http")

_clients: dict[str, httpx.AsyncClient] = {}

_CLIENT_TIMEOUTS: dict[str, float] = {
    "oauth": 15.0,
    "chat": 30.0,
    "embeddings": 60.0,
}

_CLIENT_RETRIES: dict[str, int] = {
    "oauth": 1,
    "chat": 1,
    "embeddings": 1,
}

_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


def get_ssl_verify() -> bool | str:
    cert_path = os.getenv("GIGACHAT_CERT_PATH", "").strip()
    if cert_path and os.path.isfile(cert_path):
        return cert_path
    return False


def get_shared_http_client(client_kind: str) -> httpx.AsyncClient:
    timeout = _CLIENT_TIMEOUTS.get(client_kind, 30.0)
    client = _clients.get(client_kind)
    if client is not None:
        return client

    client = httpx.AsyncClient(verify=get_ssl_verify(), timeout=timeout)
    _clients[client_kind] = client
    logger.debug("[http] initialized shared client kind=%s timeout=%s", client_kind, timeout)
    return client


async def aclose_shared_http_clients() -> None:
    if not _clients:
        return

    clients = list(_clients.items())
    _clients.clear()
    for client_kind, client in clients:
        await client.aclose()
        logger.debug("[http] closed shared client kind=%s", client_kind)


def should_retry_http_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_STATUS_CODES


async def request_json_with_policy(
    client_kind: str,
    *,
    method: str,
    url: str,
    operation: str,
    headers: dict | None = None,
    json_body: dict | None = None,
    data: dict | None = None,
    retry_count: int | None = None,
) -> dict:
    client = get_shared_http_client(client_kind)
    max_retries = _CLIENT_RETRIES.get(client_kind, 0) if retry_count is None else retry_count
    attempts = max_retries + 1
    last_exc: LLMTransportError | LLMResponseError | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = await client.request(
                method,
                url,
                headers=headers,
                json=json_body,
                data=data,
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            last_exc = LLMTransportError(f"{operation} timeout")
            retryable = True
            logger.warning("[http] %s timeout attempt=%d/%d: %s", operation, attempt, attempts, exc)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            last_exc = LLMResponseError(f"{operation} failed with status {status_code}")
            retryable = should_retry_http_status(status_code)
            logger.warning(
                "[http] %s status=%s attempt=%d/%d",
                operation,
                status_code,
                attempt,
                attempts,
            )
        except httpx.HTTPError as exc:
            last_exc = LLMTransportError(f"{operation} transport failed")
            retryable = True
            logger.warning("[http] %s transport attempt=%d/%d: %s", operation, attempt, attempts, exc)
        except ValueError as exc:
            last_exc = LLMResponseError(f"{operation} returned invalid JSON payload")
            retryable = False
            logger.warning("[http] %s invalid JSON attempt=%d/%d: %s", operation, attempt, attempts, exc)

        if attempt < attempts and retryable:
            await asyncio.sleep(0.2 * attempt)
            continue

        if last_exc is not None:
            raise last_exc

    raise LLMResponseError(f"{operation} failed without a classified error")
