"""
Resilience patterns для LLM вызовов: Circuit Breaker и Rate Limiting.

Защита от:
1. Превышения квот GigaChat
2. Каскадных ошибок при проблемах с API
3. Перегрузки системы
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger("gpt-support-llm.resilience")


# ============================================================================
# Circuit Breaker
# ============================================================================

class CircuitState(str, Enum):
    """Состояния Circuit Breaker."""
    CLOSED = "closed"      # Нормальная работа
    OPEN = "open"          # Цепь разомкнута, запросы блокируются
    HALF_OPEN = "half_open"  # Тестовый режим после таймаута


@dataclass
class CircuitBreakerConfig:
    """Конфигурация Circuit Breaker."""
    
    failure_threshold: int = 5  # Количество ошибок для открытия цепи
    success_threshold: int = 2  # Количество успехов для закрытия цепи
    timeout_seconds: int = 60   # Таймаут до перехода в HALF_OPEN
    window_seconds: int = 60    # Окно для подсчета ошибок


@dataclass
class CircuitBreakerStats:
    """Статистика Circuit Breaker."""
    
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float | None = None
    last_state_change: float = field(default_factory=time.monotonic)
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    total_rejections: int = 0


class CircuitBreakerError(Exception):
    """Ошибка при открытой цепи."""
    pass


class CircuitBreaker:
    """
    Circuit Breaker для защиты от каскадных ошибок.
    
    Паттерн:
    1. CLOSED: нормальная работа, считаем ошибки
    2. Если ошибок >= threshold → OPEN
    3. OPEN: блокируем запросы, ждем timeout
    4. После timeout → HALF_OPEN
    5. HALF_OPEN: пропускаем тестовые запросы
    6. Если успехов >= threshold → CLOSED
    7. Если ошибка → OPEN
    """
    
    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Выполнить функцию через Circuit Breaker.
        
        Args:
            func: Async функция для выполнения
            *args, **kwargs: Аргументы функции
            
        Returns:
            Результат функции
            
        Raises:
            CircuitBreakerError: Если цепь открыта
        """
        async with self._lock:
            self.stats.total_calls += 1
            
            # Проверяем состояние
            await self._update_state()
            
            if self.stats.state == CircuitState.OPEN:
                self.stats.total_rejections += 1
                logger.warning(
                    "[circuit_breaker] %s: circuit OPEN, rejecting call (failures=%d)",
                    self.name,
                    self.stats.failure_count,
                )
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is OPEN "
                    f"(failures={self.stats.failure_count})"
                )
        
        # Выполняем функцию
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        
        except Exception as exc:
            await self._on_failure()
            raise
    
    async def _update_state(self):
        """Обновить состояние Circuit Breaker."""
        now = time.monotonic()
        
        if self.stats.state == CircuitState.OPEN:
            # Проверяем таймаут
            time_since_failure = now - (self.stats.last_failure_time or 0)
            if time_since_failure >= self.config.timeout_seconds:
                self.stats.state = CircuitState.HALF_OPEN
                self.stats.success_count = 0
                self.stats.last_state_change = now
                logger.info(
                    "[circuit_breaker] %s: OPEN → HALF_OPEN (timeout expired)",
                    self.name,
                )
        
        elif self.stats.state == CircuitState.CLOSED:
            # Проверяем окно для подсчета ошибок
            time_since_change = now - self.stats.last_state_change
            if time_since_change >= self.config.window_seconds:
                # Сбрасываем счетчик ошибок
                self.stats.failure_count = 0
                self.stats.last_state_change = now
    
    async def _on_success(self):
        """Обработать успешный вызов."""
        async with self._lock:
            self.stats.total_successes += 1
            
            if self.stats.state == CircuitState.HALF_OPEN:
                self.stats.success_count += 1
                
                if self.stats.success_count >= self.config.success_threshold:
                    self.stats.state = CircuitState.CLOSED
                    self.stats.failure_count = 0
                    self.stats.success_count = 0
                    self.stats.last_state_change = time.monotonic()
                    logger.info(
                        "[circuit_breaker] %s: HALF_OPEN → CLOSED (successes=%d)",
                        self.name,
                        self.stats.success_count,
                    )
            
            elif self.stats.state == CircuitState.CLOSED:
                # Сбрасываем счетчик ошибок при успехе
                self.stats.failure_count = max(0, self.stats.failure_count - 1)
    
    async def _on_failure(self):
        """Обработать неудачный вызов."""
        async with self._lock:
            self.stats.total_failures += 1
            self.stats.failure_count += 1
            self.stats.last_failure_time = time.monotonic()
            
            if self.stats.state == CircuitState.HALF_OPEN:
                # В HALF_OPEN любая ошибка → OPEN
                self.stats.state = CircuitState.OPEN
                self.stats.last_state_change = time.monotonic()
                logger.warning(
                    "[circuit_breaker] %s: HALF_OPEN → OPEN (failure during test)",
                    self.name,
                )
            
            elif self.stats.state == CircuitState.CLOSED:
                if self.stats.failure_count >= self.config.failure_threshold:
                    self.stats.state = CircuitState.OPEN
                    self.stats.last_state_change = time.monotonic()
                    logger.error(
                        "[circuit_breaker] %s: CLOSED → OPEN (failures=%d >= threshold=%d)",
                        self.name,
                        self.stats.failure_count,
                        self.config.failure_threshold,
                    )
    
    def get_stats(self) -> dict[str, Any]:
        """Получить статистику."""
        return {
            "name": self.name,
            "state": self.stats.state.value,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "total_calls": self.stats.total_calls,
            "total_failures": self.stats.total_failures,
            "total_successes": self.stats.total_successes,
            "total_rejections": self.stats.total_rejections,
            "failure_rate": (
                self.stats.total_failures / self.stats.total_calls
                if self.stats.total_calls > 0
                else 0.0
            ),
            "rejection_rate": (
                self.stats.total_rejections / self.stats.total_calls
                if self.stats.total_calls > 0
                else 0.0
            ),
        }
    
    async def reset(self):
        """Сбросить Circuit Breaker в начальное состояние."""
        async with self._lock:
            self.stats = CircuitBreakerStats()
            logger.info("[circuit_breaker] %s: reset to CLOSED", self.name)


# ============================================================================
# Rate Limiter
# ============================================================================

@dataclass
class RateLimiterConfig:
    """Конфигурация Rate Limiter."""
    
    max_requests: int = 100  # Максимум запросов
    window_seconds: int = 60  # Временное окно
    burst_size: int = 10      # Размер burst (мгновенных запросов)


class RateLimitExceededError(Exception):
    """Ошибка превышения rate limit."""
    pass


class TokenBucketRateLimiter:
    """
    Rate Limiter на основе Token Bucket алгоритма.
    
    Принцип:
    1. Bucket содержит токены
    2. Каждый запрос забирает 1 токен
    3. Токены пополняются с постоянной скоростью
    4. Если токенов нет → запрос блокируется
    """
    
    def __init__(
        self,
        name: str,
        config: RateLimiterConfig | None = None,
    ):
        self.name = name
        self.config = config or RateLimiterConfig()
        
        # Token bucket
        self.tokens = float(self.config.burst_size)
        self.max_tokens = float(self.config.burst_size)
        self.refill_rate = self.config.max_requests / self.config.window_seconds
        self.last_refill = time.monotonic()
        
        # Статистика
        self.total_requests = 0
        self.total_allowed = 0
        self.total_rejected = 0
        
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: float = 1.0) -> bool:
        """
        Попытаться получить токены.
        
        Args:
            tokens: Количество токенов (обычно 1.0)
            
        Returns:
            True если токены получены, False если лимит превышен
        """
        async with self._lock:
            self.total_requests += 1
            
            # Пополняем токены
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(
                self.max_tokens,
                self.tokens + elapsed * self.refill_rate
            )
            self.last_refill = now
            
            # Проверяем доступность токенов
            if self.tokens >= tokens:
                self.tokens -= tokens
                self.total_allowed += 1
                return True
            else:
                self.total_rejected += 1
                logger.warning(
                    "[rate_limiter] %s: rate limit exceeded (tokens=%.2f, needed=%.2f)",
                    self.name,
                    self.tokens,
                    tokens,
                )
                return False
    
    async def wait_for_token(self, tokens: float = 1.0, timeout: float | None = None):
        """
        Ждать доступности токенов.
        
        Args:
            tokens: Количество токенов
            timeout: Максимальное время ожидания (секунды)
            
        Raises:
            RateLimitExceededError: Если таймаут истек
        """
        start = time.monotonic()
        
        while True:
            if await self.acquire(tokens):
                return
            
            # Проверяем таймаут
            if timeout is not None:
                elapsed = time.monotonic() - start
                if elapsed >= timeout:
                    raise RateLimitExceededError(
                        f"Rate limit timeout exceeded for '{self.name}'"
                    )
            
            # Ждем немного перед повторной попыткой
            await asyncio.sleep(0.1)
    
    def get_stats(self) -> dict[str, Any]:
        """Получить статистику."""
        return {
            "name": self.name,
            "tokens_available": self.tokens,
            "max_tokens": self.max_tokens,
            "refill_rate": self.refill_rate,
            "total_requests": self.total_requests,
            "total_allowed": self.total_allowed,
            "total_rejected": self.total_rejected,
            "rejection_rate": (
                self.total_rejected / self.total_requests
                if self.total_requests > 0
                else 0.0
            ),
        }
    
    async def reset(self):
        """Сбросить Rate Limiter."""
        async with self._lock:
            self.tokens = float(self.config.burst_size)
            self.last_refill = time.monotonic()
            self.total_requests = 0
            self.total_allowed = 0
            self.total_rejected = 0
            logger.info("[rate_limiter] %s: reset", self.name)


# ============================================================================
# Комбинированная защита
# ============================================================================

class ResilientLLMClient:
    """
    LLM клиент с Circuit Breaker и Rate Limiting.
    
    Обертка над GigaChatClient с защитой от:
    1. Каскадных ошибок (Circuit Breaker)
    2. Превышения квот (Rate Limiter)
    """
    
    def __init__(
        self,
        client,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        rate_limiter_config: RateLimiterConfig | None = None,
    ):
        self.client = client
        self.circuit_breaker = CircuitBreaker(
            name=f"gigachat_{client.account_id}",
            config=circuit_breaker_config,
        )
        self.rate_limiter = TokenBucketRateLimiter(
            name=f"gigachat_{client.account_id}",
            config=rate_limiter_config,
        )
    
    async def call(self, messages: list[dict], system_prompt: str) -> tuple[str, int, int, int]:
        """
        Выполнить LLM вызов с защитой.
        
        Args:
            messages: Сообщения для LLM
            system_prompt: Системный промпт
            
        Returns:
            (response_text, tokens_in, tokens_out, latency_ms)
            
        Raises:
            CircuitBreakerError: Если цепь открыта
            RateLimitExceededError: Если превышен rate limit
        """
        # Проверяем rate limit
        if not await self.rate_limiter.acquire():
            raise RateLimitExceededError(
                f"Rate limit exceeded for account {self.client.account_id}"
            )
        
        # Выполняем через circuit breaker
        return await self.circuit_breaker.call(
            self.client.call,
            messages,
            system_prompt
        )
    
    def get_stats(self) -> dict[str, Any]:
        """Получить статистику."""
        return {
            "account_id": self.client.account_id,
            "circuit_breaker": self.circuit_breaker.get_stats(),
            "rate_limiter": self.rate_limiter.get_stats(),
        }
    
    @property
    def account_id(self) -> str:
        """ID аккаунта."""
        return self.client.account_id
    
    @property
    def model_tier(self) -> str:
        """Tier модели."""
        return self.client.model_tier
    
    @property
    def is_busy(self) -> bool:
        """Занят ли клиент."""
        return self.client.is_busy
