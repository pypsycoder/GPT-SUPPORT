"""
Resilient Account Pool с Circuit Breaker и Rate Limiting.

Обертка над pool.py с добавлением:
1. Circuit Breaker для каждого аккаунта
2. Rate Limiting для каждого аккаунта
3. Мониторинг квот
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.llm.pool import AccountPool, GigaChatClient
from app.llm.resilience import (
    CircuitBreakerConfig,
    RateLimiterConfig,
    ResilientLLMClient,
    CircuitBreakerError,
    RateLimitExceededError,
)
from app.llm.errors import LLMConfigurationError

logger = logging.getLogger("gpt-support-llm.pool_resilient")


# Конфигурация из environment variables
CIRCUIT_BREAKER_ENABLED = os.getenv("LLM_CIRCUIT_BREAKER_ENABLED", "true").lower() == "true"
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv("LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
CIRCUIT_BREAKER_SUCCESS_THRESHOLD = int(os.getenv("LLM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD", "2"))
CIRCUIT_BREAKER_TIMEOUT = int(os.getenv("LLM_CIRCUIT_BREAKER_TIMEOUT", "60"))

RATE_LIMITER_ENABLED = os.getenv("LLM_RATE_LIMITER_ENABLED", "true").lower() == "true"
RATE_LIMITER_MAX_REQUESTS = int(os.getenv("LLM_RATE_LIMITER_MAX_REQUESTS", "100"))
RATE_LIMITER_WINDOW_SECONDS = int(os.getenv("LLM_RATE_LIMITER_WINDOW_SECONDS", "60"))
RATE_LIMITER_BURST_SIZE = int(os.getenv("LLM_RATE_LIMITER_BURST_SIZE", "10"))


class ResilientAccountPool:
    """
    Account Pool с Circuit Breaker и Rate Limiting.
    
    Обертка над AccountPool с добавлением resilience patterns.
    """
    
    def __init__(self):
        self.base_pool = AccountPool()
        self.resilient_clients: dict[str, ResilientLLMClient] = {}
        self._wrap_clients()
        
        logger.info(
            "[pool_resilient] initialized with circuit_breaker=%s rate_limiter=%s accounts=%d",
            CIRCUIT_BREAKER_ENABLED,
            RATE_LIMITER_ENABLED,
            len(self.base_pool.clients),
        )
    
    def _wrap_clients(self):
        """Обернуть клиенты в ResilientLLMClient."""
        circuit_config = CircuitBreakerConfig(
            failure_threshold=CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            success_threshold=CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
            timeout_seconds=CIRCUIT_BREAKER_TIMEOUT,
        ) if CIRCUIT_BREAKER_ENABLED else None
        
        rate_config = RateLimiterConfig(
            max_requests=RATE_LIMITER_MAX_REQUESTS,
            window_seconds=RATE_LIMITER_WINDOW_SECONDS,
            burst_size=RATE_LIMITER_BURST_SIZE,
        ) if RATE_LIMITER_ENABLED else None
        
        for client in self.base_pool.clients:
            if CIRCUIT_BREAKER_ENABLED or RATE_LIMITER_ENABLED:
                resilient_client = ResilientLLMClient(
                    client=client,
                    circuit_breaker_config=circuit_config,
                    rate_limiter_config=rate_config,
                )
                self.resilient_clients[client.account_id] = resilient_client
            else:
                # Без защиты - используем напрямую
                self.resilient_clients[client.account_id] = client
    
    async def get_available(self, tier: str) -> ResilientLLMClient | GigaChatClient:
        """
        Получить доступный клиент для tier.
        
        Args:
            tier: Tier модели (lite, pro, max)
            
        Returns:
            ResilientLLMClient или GigaChatClient
            
        Raises:
            LLMConfigurationError: Если нет доступных клиентов
            CircuitBreakerError: Если все цепи открыты
            RateLimitExceededError: Если все лимиты превышены
        """
        # Фильтруем клиенты по tier
        candidates = [
            (account_id, client)
            for account_id, client in self.resilient_clients.items()
            if client.model_tier == tier and not client.is_busy
        ]
        
        if not candidates:
            raise LLMConfigurationError(
                f"No available clients for tier '{tier}'"
            )
        
        # Пытаемся найти клиента с открытой цепью и доступным rate limit
        errors = []
        
        for account_id, client in candidates:
            # Проверяем circuit breaker
            if CIRCUIT_BREAKER_ENABLED:
                cb_stats = client.circuit_breaker.get_stats()
                if cb_stats["state"] == "open":
                    errors.append(f"{account_id}: circuit breaker OPEN")
                    continue
            
            # Проверяем rate limit (без блокировки)
            if RATE_LIMITER_ENABLED:
                rl_stats = client.rate_limiter.get_stats()
                if rl_stats["tokens_available"] < 1.0:
                    errors.append(f"{account_id}: rate limit exceeded")
                    continue
            
            # Клиент доступен
            logger.debug(
                "[pool_resilient] selected account=%s tier=%s",
                account_id,
                tier,
            )
            return client
        
        # Все клиенты недоступны
        error_msg = f"All clients for tier '{tier}' are unavailable: {'; '.join(errors)}"
        logger.error("[pool_resilient] %s", error_msg)
        raise LLMConfigurationError(error_msg)
    
    def get_stats(self) -> dict[str, Any]:
        """Получить статистику всех клиентов."""
        stats = {
            "total_clients": len(self.resilient_clients),
            "circuit_breaker_enabled": CIRCUIT_BREAKER_ENABLED,
            "rate_limiter_enabled": RATE_LIMITER_ENABLED,
            "clients": {},
        }
        
        for account_id, client in self.resilient_clients.items():
            if isinstance(client, ResilientLLMClient):
                stats["clients"][account_id] = client.get_stats()
            else:
                stats["clients"][account_id] = {
                    "account_id": account_id,
                    "model_tier": client.model_tier,
                    "is_busy": client.is_busy,
                }
        
        return stats
    
    def get_health_status(self) -> dict[str, Any]:
        """Получить health status пула."""
        stats = self.get_stats()
        
        total = stats["total_clients"]
        healthy = 0
        degraded = 0
        unhealthy = 0
        
        for client_stats in stats["clients"].values():
            if "circuit_breaker" not in client_stats:
                healthy += 1
                continue
            
            cb_state = client_stats["circuit_breaker"]["state"]
            rl_rejection_rate = client_stats["rate_limiter"]["rejection_rate"]
            
            if cb_state == "open":
                unhealthy += 1
            elif cb_state == "half_open" or rl_rejection_rate > 0.5:
                degraded += 1
            else:
                healthy += 1
        
        overall_status = "healthy"
        if unhealthy > total / 2:
            overall_status = "unhealthy"
        elif degraded > 0 or unhealthy > 0:
            overall_status = "degraded"
        
        return {
            "status": overall_status,
            "total_clients": total,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "details": stats,
        }


# Глобальный экземпляр resilient pool
resilient_pool = ResilientAccountPool()


# Функция для получения статистики (для мониторинга)
def get_pool_stats() -> dict[str, Any]:
    """Получить статистику пула."""
    return resilient_pool.get_stats()


def get_pool_health() -> dict[str, Any]:
    """Получить health status пула."""
    return resilient_pool.get_health_status()
