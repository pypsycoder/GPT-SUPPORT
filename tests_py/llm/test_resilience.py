"""
Тесты для resilience patterns: Circuit Breaker и Rate Limiting.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.llm.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
    TokenBucketRateLimiter,
    RateLimiterConfig,
    RateLimitExceededError,
    ResilientLLMClient,
)


class TestCircuitBreaker:
    """Тесты для Circuit Breaker."""
    
    @pytest.mark.asyncio
    async def test_closed_state_allows_calls(self):
        """Проверяет, что CLOSED состояние пропускает вызовы."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        
        async def success_func():
            return "success"
        
        result = await cb.call(success_func)
        assert result == "success"
        assert cb.stats.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        """Проверяет открытие цепи после threshold ошибок."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        
        async def failing_func():
            raise ValueError("Test error")
        
        # Первые 2 ошибки - цепь остается закрытой
        for i in range(2):
            with pytest.raises(ValueError):
                await cb.call(failing_func)
            assert cb.stats.state == CircuitState.CLOSED
        
        # 3-я ошибка - цепь открывается
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        assert cb.stats.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_rejects_calls_when_open(self):
        """Проверяет блокировку вызовов при открытой цепи."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))
        
        async def failing_func():
            raise ValueError("Test error")
        
        # Открываем цепь
        for i in range(2):
            with pytest.raises(ValueError):
                await cb.call(failing_func)
        
        assert cb.stats.state == CircuitState.OPEN
        
        # Следующий вызов должен быть заблокирован
        async def success_func():
            return "success"
        
        with pytest.raises(CircuitBreakerError):
            await cb.call(success_func)
    
    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        """Проверяет переход в HALF_OPEN после таймаута."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=2, timeout_seconds=1)
        )
        
        async def failing_func():
            raise ValueError("Test error")
        
        # Открываем цепь
        for i in range(2):
            with pytest.raises(ValueError):
                await cb.call(failing_func)
        
        assert cb.stats.state == CircuitState.OPEN
        
        # Ждем таймаут
        await asyncio.sleep(1.1)
        
        # Проверяем состояние (должно обновиться при следующем вызове)
        async def success_func():
            return "success"
        
        result = await cb.call(success_func)
        assert result == "success"
        # После успешного вызова в HALF_OPEN может перейти в CLOSED
    
    @pytest.mark.asyncio
    async def test_closes_after_success_threshold(self):
        """Проверяет закрытие цепи после threshold успехов."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(
                failure_threshold=2,
                success_threshold=2,
                timeout_seconds=1
            )
        )
        
        async def failing_func():
            raise ValueError("Test error")
        
        async def success_func():
            return "success"
        
        # Открываем цепь
        for i in range(2):
            with pytest.raises(ValueError):
                await cb.call(failing_func)
        
        assert cb.stats.state == CircuitState.OPEN
        
        # Ждем таймаут
        await asyncio.sleep(1.1)
        
        # 2 успешных вызова в HALF_OPEN
        for i in range(2):
            result = await cb.call(success_func)
            assert result == "success"
        
        # Цепь должна закрыться
        assert cb.stats.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_reopens_on_failure_in_half_open(self):
        """Проверяет повторное открытие при ошибке в HALF_OPEN."""
        cb = CircuitBreaker(
            "test",
            CircuitBreakerConfig(failure_threshold=2, timeout_seconds=1)
        )
        
        async def failing_func():
            raise ValueError("Test error")
        
        # Открываем цепь
        for i in range(2):
            with pytest.raises(ValueError):
                await cb.call(failing_func)
        
        assert cb.stats.state == CircuitState.OPEN
        
        # Ждем таймаут
        await asyncio.sleep(1.1)
        
        # Ошибка в HALF_OPEN → снова OPEN
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        
        assert cb.stats.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Проверяет получение статистики."""
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        
        async def success_func():
            return "success"
        
        async def failing_func():
            raise ValueError("Test error")
        
        # Несколько вызовов
        await cb.call(success_func)
        await cb.call(success_func)
        
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        
        stats = cb.get_stats()
        
        assert stats["name"] == "test"
        assert stats["state"] == "closed"
        assert stats["total_calls"] == 3
        assert stats["total_successes"] == 2
        assert stats["total_failures"] == 1
        assert stats["failure_rate"] == pytest.approx(1/3)


class TestTokenBucketRateLimiter:
    """Тесты для Rate Limiter."""
    
    @pytest.mark.asyncio
    async def test_allows_requests_within_limit(self):
        """Проверяет пропуск запросов в пределах лимита."""
        rl = TokenBucketRateLimiter(
            "test",
            RateLimiterConfig(max_requests=10, window_seconds=1, burst_size=5)
        )
        
        # Первые 5 запросов (burst) должны пройти
        for i in range(5):
            assert await rl.acquire() is True
    
    @pytest.mark.asyncio
    async def test_rejects_requests_over_limit(self):
        """Проверяет блокировку запросов при превышении лимита."""
        rl = TokenBucketRateLimiter(
            "test",
            RateLimiterConfig(max_requests=10, window_seconds=1, burst_size=3)
        )
        
        # Первые 3 запроса проходят
        for i in range(3):
            assert await rl.acquire() is True
        
        # 4-й запрос блокируется
        assert await rl.acquire() is False
    
    @pytest.mark.asyncio
    async def test_refills_tokens_over_time(self):
        """Проверяет пополнение токенов со временем."""
        rl = TokenBucketRateLimiter(
            "test",
            RateLimiterConfig(max_requests=10, window_seconds=1, burst_size=2)
        )
        
        # Используем все токены
        assert await rl.acquire() is True
        assert await rl.acquire() is True
        assert await rl.acquire() is False
        
        # Ждем пополнения (10 req/sec = 1 token за 0.1 sec)
        await asyncio.sleep(0.15)
        
        # Должен появиться новый токен
        assert await rl.acquire() is True
    
    @pytest.mark.asyncio
    async def test_wait_for_token(self):
        """Проверяет ожидание доступности токенов."""
        rl = TokenBucketRateLimiter(
            "test",
            RateLimiterConfig(max_requests=10, window_seconds=1, burst_size=1)
        )
        
        # Используем токен
        assert await rl.acquire() is True
        
        # Ждем следующий токен (должен появиться через ~0.1 сек)
        await rl.wait_for_token(timeout=0.5)
        
        # Токен получен
        assert rl.total_allowed == 2
    
    @pytest.mark.asyncio
    async def test_wait_for_token_timeout(self):
        """Проверяет таймаут при ожидании токенов."""
        rl = TokenBucketRateLimiter(
            "test",
            RateLimiterConfig(max_requests=1, window_seconds=10, burst_size=1)
        )
        
        # Используем токен
        assert await rl.acquire() is True
        
        # Ждем с коротким таймаутом (токен не успеет появиться)
        with pytest.raises(RateLimitExceededError):
            await rl.wait_for_token(timeout=0.1)
    
    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Проверяет получение статистики."""
        rl = TokenBucketRateLimiter(
            "test",
            RateLimiterConfig(max_requests=10, window_seconds=1, burst_size=3)
        )
        
        # Несколько запросов
        await rl.acquire()
        await rl.acquire()
        await rl.acquire()
        await rl.acquire()  # Этот будет отклонен
        
        stats = rl.get_stats()
        
        assert stats["name"] == "test"
        assert stats["total_requests"] == 4
        assert stats["total_allowed"] == 3
        assert stats["total_rejected"] == 1
        assert stats["rejection_rate"] == 0.25


class TestResilientLLMClient:
    """Тесты для ResilientLLMClient."""
    
    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Проверяет успешный вызов."""
        mock_client = AsyncMock()
        mock_client.account_id = "test_account"
        mock_client.model_tier = "pro"
        mock_client.is_busy = False
        mock_client.call = AsyncMock(return_value=("response", 100, 50, 1000))
        
        resilient = ResilientLLMClient(
            client=mock_client,
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3),
            rate_limiter_config=RateLimiterConfig(max_requests=10, window_seconds=1, burst_size=5),
        )
        
        result = await resilient.call([], "system prompt")
        
        assert result == ("response", 100, 50, 1000)
        mock_client.call.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_protection(self):
        """Проверяет защиту Circuit Breaker."""
        mock_client = AsyncMock()
        mock_client.account_id = "test_account"
        mock_client.model_tier = "pro"
        mock_client.is_busy = False
        mock_client.call = AsyncMock(side_effect=ValueError("API error"))
        
        resilient = ResilientLLMClient(
            client=mock_client,
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=2),
            rate_limiter_config=None,
        )
        
        # Первые 2 ошибки проходят
        for i in range(2):
            with pytest.raises(ValueError):
                await resilient.call([], "system prompt")
        
        # 3-й вызов блокируется Circuit Breaker
        with pytest.raises(CircuitBreakerError):
            await resilient.call([], "system prompt")
    
    @pytest.mark.asyncio
    async def test_rate_limiter_protection(self):
        """Проверяет защиту Rate Limiter."""
        mock_client = AsyncMock()
        mock_client.account_id = "test_account"
        mock_client.model_tier = "pro"
        mock_client.is_busy = False
        mock_client.call = AsyncMock(return_value=("response", 100, 50, 1000))
        
        resilient = ResilientLLMClient(
            client=mock_client,
            circuit_breaker_config=None,
            rate_limiter_config=RateLimiterConfig(max_requests=10, window_seconds=1, burst_size=2),
        )
        
        # Первые 2 вызова проходят
        await resilient.call([], "system prompt")
        await resilient.call([], "system prompt")
        
        # 3-й вызов блокируется Rate Limiter
        with pytest.raises(RateLimitExceededError):
            await resilient.call([], "system prompt")
    
    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Проверяет получение статистики."""
        mock_client = AsyncMock()
        mock_client.account_id = "test_account"
        mock_client.model_tier = "pro"
        mock_client.is_busy = False
        mock_client.call = AsyncMock(return_value=("response", 100, 50, 1000))
        
        resilient = ResilientLLMClient(
            client=mock_client,
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3),
            rate_limiter_config=RateLimiterConfig(max_requests=10, window_seconds=1, burst_size=5),
        )
        
        await resilient.call([], "system prompt")
        
        stats = resilient.get_stats()
        
        assert stats["account_id"] == "test_account"
        assert "circuit_breaker" in stats
        assert "rate_limiter" in stats
        assert stats["circuit_breaker"]["total_calls"] == 1
        assert stats["rate_limiter"]["total_requests"] == 1
