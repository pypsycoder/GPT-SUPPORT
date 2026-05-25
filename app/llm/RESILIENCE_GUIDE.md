# Руководство по Resilience Patterns

## Обзор

Реализованы критические паттерны устойчивости для защиты от сбоев GigaChat API и превышения квот.

## 🛡️ Реализованные паттерны

### 1. Circuit Breaker

**Назначение:** Защита от каскадных ошибок при проблемах с API

**Принцип работы:**

```
CLOSED (нормальная работа)
    ↓ (failures >= threshold)
OPEN (блокировка запросов)
    ↓ (timeout истек)
HALF_OPEN (тестовый режим)
    ↓ (successes >= threshold)
CLOSED
```

**Состояния:**

- **CLOSED** - нормальная работа, запросы проходят
- **OPEN** - цепь разомкнута, запросы блокируются
- **HALF_OPEN** - тестовый режим после таймаута

**Конфигурация:**

```python
CircuitBreakerConfig(
    failure_threshold=5,    # Ошибок для открытия цепи
    success_threshold=2,    # Успехов для закрытия цепи
    timeout_seconds=60,     # Таймаут до HALF_OPEN
    window_seconds=60,      # Окно для подсчета ошибок
)
```

### 2. Rate Limiting

**Назначение:** Защита от превышения квот GigaChat

**Алгоритм:** Token Bucket

**Принцип работы:**

1. Bucket содержит токены
2. Каждый запрос забирает 1 токен
3. Токены пополняются с постоянной скоростью
4. Если токенов нет → запрос блокируется

**Конфигурация:**

```python
RateLimiterConfig(
    max_requests=100,       # Максимум запросов
    window_seconds=60,      # Временное окно (60 сек)
    burst_size=10,          # Размер burst (мгновенных запросов)
)
```

**Пример:** 100 req/min = 1.67 req/sec, burst до 10 запросов

## 🚀 Использование

### Включение защиты

```bash
# Circuit Breaker (по умолчанию включен)
export LLM_CIRCUIT_BREAKER_ENABLED=true
export LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
export LLM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2
export LLM_CIRCUIT_BREAKER_TIMEOUT=60

# Rate Limiting (по умолчанию включен)
export LLM_RATE_LIMITER_ENABLED=true
export LLM_RATE_LIMITER_MAX_REQUESTS=100
export LLM_RATE_LIMITER_WINDOW_SECONDS=60
export LLM_RATE_LIMITER_BURST_SIZE=10
```

### Использование в коде

```python
from app.llm.pool_resilient import resilient_pool

# Получить клиента с защитой
client = await resilient_pool.get_available("pro")

# Выполнить запрос (автоматически защищен)
try:
    response, tokens_in, tokens_out, latency = await client.call(
        messages=[{"role": "user", "content": "Hello"}],
        system_prompt="You are a helpful assistant"
    )
except CircuitBreakerError:
    # Цепь открыта - API недоступен
    logger.error("Circuit breaker is OPEN")
except RateLimitExceededError:
    # Превышен rate limit
    logger.error("Rate limit exceeded")
```

### Мониторинг

```python
from app.llm.pool_resilient import get_pool_stats, get_pool_health

# Статистика всех клиентов
stats = get_pool_stats()
print(f"Total clients: {stats['total_clients']}")

for account_id, client_stats in stats['clients'].items():
    cb = client_stats['circuit_breaker']
    rl = client_stats['rate_limiter']
    
    print(f"\nAccount: {account_id}")
    print(f"  Circuit Breaker: {cb['state']}")
    print(f"  Failures: {cb['failure_count']}")
    print(f"  Rate Limiter: {rl['tokens_available']:.2f} tokens")
    print(f"  Rejection rate: {rl['rejection_rate']:.2%}")

# Health status
health = get_pool_health()
print(f"\nOverall status: {health['status']}")
print(f"Healthy: {health['healthy']}/{health['total_clients']}")
print(f"Degraded: {health['degraded']}/{health['total_clients']}")
print(f"Unhealthy: {health['unhealthy']}/{health['total_clients']}")
```

## 📊 Метрики

### Circuit Breaker метрики

```python
cb_stats = client.circuit_breaker.get_stats()

{
    "name": "gigachat_A1",
    "state": "closed",              # closed | open | half_open
    "failure_count": 2,             # Текущие ошибки
    "success_count": 0,             # Текущие успехи (в HALF_OPEN)
    "total_calls": 100,             # Всего вызовов
    "total_failures": 5,            # Всего ошибок
    "total_successes": 95,          # Всего успехов
    "total_rejections": 0,          # Всего отклонено
    "failure_rate": 0.05,           # 5% ошибок
    "rejection_rate": 0.0,          # 0% отклонено
}
```

### Rate Limiter метрики

```python
rl_stats = client.rate_limiter.get_stats()

{
    "name": "gigachat_A1",
    "tokens_available": 8.5,        # Доступно токенов
    "max_tokens": 10.0,             # Максимум токенов
    "refill_rate": 1.67,            # Скорость пополнения (req/sec)
    "total_requests": 150,          # Всего запросов
    "total_allowed": 145,           # Разрешено
    "total_rejected": 5,            # Отклонено
    "rejection_rate": 0.033,        # 3.3% отклонено
}
```

## 🔍 Диагностика

### Проверка состояния Circuit Breaker

```python
stats = client.circuit_breaker.get_stats()

if stats["state"] == "open":
    print(f"⚠️ Circuit breaker OPEN!")
    print(f"Failures: {stats['failure_count']}")
    print(f"Wait for timeout: {CIRCUIT_BREAKER_TIMEOUT} seconds")

elif stats["state"] == "half_open":
    print(f"🔄 Circuit breaker HALF_OPEN (testing)")
    print(f"Successes needed: {CIRCUIT_BREAKER_SUCCESS_THRESHOLD}")

else:
    print(f"✅ Circuit breaker CLOSED (healthy)")
```

### Проверка Rate Limit

```python
stats = client.rate_limiter.get_stats()

if stats["tokens_available"] < 1.0:
    print(f"⚠️ Rate limit exceeded!")
    print(f"Tokens available: {stats['tokens_available']:.2f}")
    print(f"Refill rate: {stats['refill_rate']:.2f} req/sec")
    
    # Время до следующего токена
    wait_time = (1.0 - stats["tokens_available"]) / stats["refill_rate"]
    print(f"Wait time: {wait_time:.2f} seconds")

else:
    print(f"✅ Rate limit OK")
    print(f"Tokens available: {stats['tokens_available']:.2f}")
```

## 🎯 Рекомендации по настройке

### Circuit Breaker

**Для production:**
```bash
LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5   # 5 ошибок подряд
LLM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2   # 2 успеха для восстановления
LLM_CIRCUIT_BREAKER_TIMEOUT=60            # 1 минута до retry
```

**Для агрессивной защиты:**
```bash
LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=3   # Быстрее открывается
LLM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3   # Медленнее закрывается
LLM_CIRCUIT_BREAKER_TIMEOUT=120           # Дольше ждет
```

**Для мягкой защиты:**
```bash
LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=10  # Терпимее к ошибкам
LLM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=1   # Быстрее восстанавливается
LLM_CIRCUIT_BREAKER_TIMEOUT=30            # Быстрее retry
```

### Rate Limiting

**Для GigaChat квот (пример: 100 req/min):**
```bash
LLM_RATE_LIMITER_MAX_REQUESTS=100         # 100 запросов
LLM_RATE_LIMITER_WINDOW_SECONDS=60        # За 60 секунд
LLM_RATE_LIMITER_BURST_SIZE=10            # Burst до 10
```

**Для консервативного подхода (80% квоты):**
```bash
LLM_RATE_LIMITER_MAX_REQUESTS=80          # 80% от лимита
LLM_RATE_LIMITER_WINDOW_SECONDS=60
LLM_RATE_LIMITER_BURST_SIZE=5             # Меньший burst
```

## 🚨 Алерты и мониторинг

### Критические алерты

1. **Circuit Breaker OPEN**
   ```python
   if cb_stats["state"] == "open":
       alert("Circuit breaker OPEN for account {account_id}")
   ```

2. **High rejection rate**
   ```python
   if rl_stats["rejection_rate"] > 0.1:  # >10%
       alert("High rate limit rejection rate: {rejection_rate:.2%}")
   ```

3. **Multiple accounts unhealthy**
   ```python
   health = get_pool_health()
   if health["unhealthy"] > health["total_clients"] / 2:
       alert("More than 50% accounts unhealthy")
   ```

### Prometheus metrics (рекомендуется)

```python
from prometheus_client import Gauge, Counter

# Circuit Breaker
circuit_breaker_state = Gauge(
    'llm_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=half_open, 2=open)',
    ['account_id']
)

circuit_breaker_failures = Counter(
    'llm_circuit_breaker_failures_total',
    'Total circuit breaker failures',
    ['account_id']
)

# Rate Limiter
rate_limiter_rejections = Counter(
    'llm_rate_limiter_rejections_total',
    'Total rate limiter rejections',
    ['account_id']
)

rate_limiter_tokens = Gauge(
    'llm_rate_limiter_tokens_available',
    'Available rate limiter tokens',
    ['account_id']
)
```

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты resilience
pytest tests_py/llm/test_resilience.py -v

# Конкретный тест
pytest tests_py/llm/test_resilience.py::TestCircuitBreaker::test_opens_after_threshold_failures -v

# С покрытием
pytest tests_py/llm/test_resilience.py --cov=app.llm.resilience
```

### Ручное тестирование

```python
# Тест Circuit Breaker
from app.llm.resilience import CircuitBreaker, CircuitBreakerConfig

cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))

async def failing_func():
    raise ValueError("Test error")

# Открываем цепь
for i in range(3):
    try:
        await cb.call(failing_func)
    except ValueError:
        pass

# Проверяем состояние
assert cb.stats.state == "open"

# Тест Rate Limiter
from app.llm.resilience import TokenBucketRateLimiter, RateLimiterConfig

rl = TokenBucketRateLimiter("test", RateLimiterConfig(
    max_requests=10,
    window_seconds=1,
    burst_size=3
))

# Используем burst
for i in range(3):
    assert await rl.acquire() is True

# Следующий блокируется
assert await rl.acquire() is False
```

## 📝 Best Practices

### 1. Мониторинг обязателен

Всегда мониторьте состояние Circuit Breaker и Rate Limiter:

```python
# Периодическая проверка (каждые 30 секунд)
async def monitor_resilience():
    while True:
        health = get_pool_health()
        logger.info(f"Pool health: {health['status']}")
        
        if health['status'] != 'healthy':
            logger.warning(f"Pool degraded: {health}")
        
        await asyncio.sleep(30)
```

### 2. Graceful degradation

При проблемах с API используйте fallback:

```python
try:
    client = await resilient_pool.get_available("pro")
    response = await client.call(messages, system_prompt)
except (CircuitBreakerError, RateLimitExceededError):
    # Fallback на кэшированный ответ или упрощенную логику
    response = get_cached_response() or get_fallback_response()
```

### 3. Логирование

Логируйте все события resilience:

```python
# Логи автоматически пишутся в app.llm.resilience logger
[circuit_breaker] gigachat_A1: CLOSED → OPEN (failures=5 >= threshold=5)
[rate_limiter] gigachat_A1: rate limit exceeded (tokens=0.00, needed=1.00)
[pool_resilient] All clients for tier 'pro' are unavailable
```

### 4. Тестирование в staging

Перед production протестируйте с реальными квотами:

```bash
# Установите реальные лимиты
export LLM_RATE_LIMITER_MAX_REQUESTS=100  # Ваша квота
export LLM_RATE_LIMITER_WINDOW_SECONDS=60

# Запустите нагрузочный тест
python scripts/load_test_llm.py --requests=150 --duration=60
```

## 🔧 Troubleshooting

### Проблема: Circuit Breaker постоянно OPEN

**Причины:**
1. Реальные проблемы с GigaChat API
2. Слишком низкий failure_threshold
3. Проблемы с сетью

**Решение:**
```bash
# Проверьте логи
grep "circuit_breaker" logs/app.log

# Увеличьте threshold
export LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=10

# Или отключите временно
export LLM_CIRCUIT_BREAKER_ENABLED=false
```

### Проблема: Частые rate limit rejections

**Причины:**
1. Превышение реальной квоты GigaChat
2. Слишком низкий max_requests
3. Много одновременных запросов

**Решение:**
```bash
# Увеличьте лимит (если квота позволяет)
export LLM_RATE_LIMITER_MAX_REQUESTS=200

# Или увеличьте burst
export LLM_RATE_LIMITER_BURST_SIZE=20

# Или распределите нагрузку
# (добавьте больше аккаунтов)
```

### Проблема: Все аккаунты unavailable

**Причины:**
1. Все Circuit Breakers OPEN
2. Все Rate Limiters исчерпаны
3. Проблемы с GigaChat

**Решение:**
```python
# Проверьте health
health = get_pool_health()
print(health)

# Сбросьте Circuit Breakers
for client in resilient_pool.resilient_clients.values():
    await client.circuit_breaker.reset()

# Или отключите защиту временно
export LLM_CIRCUIT_BREAKER_ENABLED=false
export LLM_RATE_LIMITER_ENABLED=false
```

## 📚 Дополнительные ресурсы

- **Код:** [`app/llm/resilience.py`](app/llm/resilience.py:1)
- **Pool:** [`app/llm/pool_resilient.py`](app/llm/pool_resilient.py:1)
- **Тесты:** [`tests_py/llm/test_resilience.py`](tests_py/llm/test_resilience.py:1)
- **Паттерны:** [Microsoft Azure - Circuit Breaker Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
