"""
Тесты для оптимизированного context builder.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from app.llm.context_builder_optimized import (
    PatientSummaryCache,
    RAGCache,
    build_context_bundle_optimized,
    invalidate_patient_cache,
    clear_all_caches,
    get_cache_stats,
)


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock()


class TestPatientSummaryCache:
    """Тесты для кэша patient summary."""
    
    @pytest.mark.asyncio
    async def test_cache_miss(self):
        """Проверяет cache miss."""
        cache = PatientSummaryCache(ttl_seconds=300)
        result = await cache.get(patient_id=1)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Проверяет cache hit."""
        cache = PatientSummaryCache(ttl_seconds=300)
        summary = [{"text": "Test summary", "tags": ["test"], "priority": 100}]
        
        await cache.set(patient_id=1, summary=summary)
        result = await cache.get(patient_id=1)
        
        assert result is not None
        assert result == summary
    
    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        """Проверяет истечение TTL."""
        cache = PatientSummaryCache(ttl_seconds=1)
        summary = [{"text": "Test summary", "tags": ["test"], "priority": 100}]
        
        await cache.set(patient_id=1, summary=summary)
        
        # Сразу после записи - должен быть hit
        result = await cache.get(patient_id=1)
        assert result is not None
        
        # Ждем истечения TTL
        import asyncio
        await asyncio.sleep(1.1)
        
        # После истечения - должен быть miss
        result = await cache.get(patient_id=1)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self):
        """Проверяет инвалидацию кэша."""
        cache = PatientSummaryCache(ttl_seconds=300)
        summary = [{"text": "Test summary", "tags": ["test"], "priority": 100}]
        
        await cache.set(patient_id=1, summary=summary)
        await cache.invalidate(patient_id=1)
        
        result = await cache.get(patient_id=1)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_clear(self):
        """Проверяет очистку всего кэша."""
        cache = PatientSummaryCache(ttl_seconds=300)
        
        await cache.set(patient_id=1, summary=[{"text": "Summary 1"}])
        await cache.set(patient_id=2, summary=[{"text": "Summary 2"}])
        
        await cache.clear()
        
        assert await cache.get(patient_id=1) is None
        assert await cache.get(patient_id=2) is None


class TestRAGCache:
    """Тесты для кэша RAG результатов."""
    
    @pytest.mark.asyncio
    async def test_cache_miss(self):
        """Проверяет cache miss."""
        cache = RAGCache(ttl_seconds=600)
        result = await cache.get(patient_id=1, query="test query")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Проверяет cache hit."""
        cache = RAGCache(ttl_seconds=600)
        rag_result = (
            ["Урок 1", "Урок 2"],
            {"hit_count": 2},
            [{"lesson_id": 1}, {"lesson_id": 2}]
        )
        
        await cache.set(patient_id=1, query="test query", result=rag_result)
        result = await cache.get(patient_id=1, query="test query")
        
        assert result is not None
        assert result == rag_result
    
    @pytest.mark.asyncio
    async def test_query_normalization(self):
        """Проверяет нормализацию query для кэша."""
        cache = RAGCache(ttl_seconds=600)
        rag_result = (["Урок 1"], {}, [])
        
        # Разные варианты одного query
        await cache.set(patient_id=1, query="  Test   Query  ", result=rag_result)
        
        # Должны получить тот же результат
        result1 = await cache.get(patient_id=1, query="test query")
        result2 = await cache.get(patient_id=1, query="TEST QUERY")
        result3 = await cache.get(patient_id=1, query="  test   query  ")
        
        assert result1 == rag_result
        assert result2 == rag_result
        assert result3 == rag_result
    
    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        """Проверяет истечение TTL."""
        cache = RAGCache(ttl_seconds=1)
        rag_result = (["Урок 1"], {}, [])
        
        await cache.set(patient_id=1, query="test", result=rag_result)
        
        # Сразу - hit
        result = await cache.get(patient_id=1, query="test")
        assert result is not None
        
        # После истечения - miss
        import asyncio
        await asyncio.sleep(1.1)
        
        result = await cache.get(patient_id=1, query="test")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_by_patient(self):
        """Проверяет инвалидацию по patient_id."""
        cache = RAGCache(ttl_seconds=600)
        
        await cache.set(patient_id=1, query="query1", result=(["A"], {}, []))
        await cache.set(patient_id=1, query="query2", result=(["B"], {}, []))
        await cache.set(patient_id=2, query="query1", result=(["C"], {}, []))
        
        await cache.invalidate(patient_id=1)
        
        # Patient 1 - miss
        assert await cache.get(patient_id=1, query="query1") is None
        assert await cache.get(patient_id=1, query="query2") is None
        
        # Patient 2 - hit
        assert await cache.get(patient_id=2, query="query1") is not None


class TestOptimizedContextBuilder:
    """Тесты для оптимизированного context builder."""
    
    @pytest.mark.asyncio
    async def test_parallel_queries(self, mock_db):
        """Проверяет параллельное выполнение запросов."""
        with patch("app.llm.context_builder_optimized._get_recent_vitals") as mock_vitals, \
             patch("app.llm.context_builder_optimized._get_medication_adherence") as mock_meds, \
             patch("app.llm.context_builder_optimized._get_sleep_summary") as mock_sleep:
            
            # Мокаем функции
            mock_vitals.return_value = ["АД 120/80"]
            mock_meds.return_value = ["Приём: 90%"]
            mock_sleep.return_value = ["Сон: 7ч"]
            
            result = await build_context_bundle_optimized(
                patient_id=1,
                db=mock_db,
                query=""
            )
            
            # Проверяем, что все функции были вызваны
            mock_vitals.assert_called_once()
            mock_meds.assert_called_once()
            mock_sleep.assert_called_once()
            
            # Проверяем результат
            assert "recent_vitals" in result["context"]
            assert "medication_adherence" in result["context"]
            assert "sleep_summary" in result["context"]
            
            # Проверяем диагностику
            assert result["diagnostics"]["optimization"]["parallel_queries"] is True
            assert "parallel_latency_ms" in result["diagnostics"]["optimization"]
    
    @pytest.mark.asyncio
    async def test_summary_cache_hit(self, mock_db):
        """Проверяет cache hit для patient summary."""
        # Очищаем кэш
        await clear_all_caches()
        
        with patch("app.llm.context_builder_optimized._build_patient_summary_items") as mock_build:
            mock_build.return_value = [{"text": "Test", "tags": [], "priority": 100}]
            
            # Первый запрос - cache miss
            result1 = await build_context_bundle_optimized(
                patient_id=1,
                db=mock_db,
                query=""
            )
            
            assert "patient_summary" in result1["diagnostics"]["cache_misses"]
            assert mock_build.call_count == 1
            
            # Второй запрос - cache hit
            result2 = await build_context_bundle_optimized(
                patient_id=1,
                db=mock_db,
                query=""
            )
            
            assert "patient_summary" in result2["diagnostics"]["cache_hits"]
            assert mock_build.call_count == 1  # Не должен вызываться повторно
    
    @pytest.mark.asyncio
    async def test_rag_cache_hit(self, mock_db):
        """Проверяет cache hit для RAG."""
        # Очищаем кэш
        await clear_all_caches()
        
        with patch("app.rag.retriever.retrieve_relevant_modules_with_meta") as mock_rag:
            mock_rag.return_value = {
                "modules": [{"title": "Урок 1", "chunk": "Текст"}],
                "meta": {"hit_count": 1},
            }
            
            # Первый запрос - cache miss
            result1 = await build_context_bundle_optimized(
                patient_id=1,
                db=mock_db,
                query="не могу уснуть"
            )
            
            assert "rag" in result1["diagnostics"]["cache_misses"]
            assert mock_rag.call_count == 1
            
            # Второй запрос с тем же query - cache hit
            result2 = await build_context_bundle_optimized(
                patient_id=1,
                db=mock_db,
                query="не могу уснуть"
            )
            
            assert "rag" in result2["diagnostics"]["cache_hits"]
            assert mock_rag.call_count == 1  # Не должен вызываться повторно
            assert result2["diagnostics"]["rag"]["cache_hit"] is True
    
    @pytest.mark.asyncio
    async def test_graceful_degradation(self, mock_db):
        """Проверяет graceful degradation при ошибках."""
        with patch("app.llm.context_builder_optimized._get_recent_vitals") as mock_vitals, \
             patch("app.llm.context_builder_optimized._get_sleep_summary") as mock_sleep:
            
            # Одна функция падает
            mock_vitals.side_effect = Exception("Database error")
            mock_sleep.return_value = ["Сон: 7ч"]
            
            result = await build_context_bundle_optimized(
                patient_id=1,
                db=mock_db,
                query=""
            )
            
            # Проверяем, что упавший раздел вернул []
            assert result["context"]["recent_vitals"] == []
            assert "recent_vitals" in result["diagnostics"]["sections_failed"]
            
            # Проверяем, что успешный раздел работает
            assert result["context"]["sleep_summary"] == ["Сон: 7ч"]
            assert "sleep_summary" in result["diagnostics"]["sections_ok"]
    
    @pytest.mark.asyncio
    async def test_latency_improvement(self, mock_db):
        """Проверяет улучшение латентности."""
        import asyncio
        
        async def slow_query(*args, **kwargs):
            await asyncio.sleep(0.05)  # 50ms
            return ["result"]
        
        with patch("app.llm.context_builder_optimized._get_recent_vitals", side_effect=slow_query), \
             patch("app.llm.context_builder_optimized._get_medication_adherence", side_effect=slow_query), \
             patch("app.llm.context_builder_optimized._get_sleep_summary", side_effect=slow_query):
            
            result = await build_context_bundle_optimized(
                patient_id=1,
                db=mock_db,
                query=""
            )
            
            # Параллельное выполнение должно быть быстрее последовательного
            # 3 запроса по 50ms параллельно = ~50ms вместо 150ms
            parallel_latency = result["diagnostics"]["optimization"]["parallel_latency_ms"]
            assert parallel_latency < 100  # Должно быть меньше 100ms


class TestCacheUtilities:
    """Тесты для утилит управления кэшем."""
    
    @pytest.mark.asyncio
    async def test_invalidate_patient_cache(self):
        """Проверяет инвалидацию кэша пациента."""
        from app.llm.context_builder_optimized import _summary_cache, _rag_cache
        
        await _summary_cache.set(1, [{"text": "Summary"}])
        await _rag_cache.set(1, "query", ([], {}, []))
        
        await invalidate_patient_cache(1)
        
        assert await _summary_cache.get(1) is None
        assert await _rag_cache.get(1, "query") is None
    
    @pytest.mark.asyncio
    async def test_clear_all_caches(self):
        """Проверяет очистку всех кэшей."""
        from app.llm.context_builder_optimized import _summary_cache, _rag_cache
        
        await _summary_cache.set(1, [{"text": "Summary 1"}])
        await _summary_cache.set(2, [{"text": "Summary 2"}])
        await _rag_cache.set(1, "query1", ([], {}, []))
        await _rag_cache.set(2, "query2", ([], {}, []))
        
        await clear_all_caches()
        
        assert await _summary_cache.get(1) is None
        assert await _summary_cache.get(2) is None
        assert await _rag_cache.get(1, "query1") is None
        assert await _rag_cache.get(2, "query2") is None
    
    def test_get_cache_stats(self):
        """Проверяет получение статистики кэшей."""
        stats = get_cache_stats()
        
        assert "summary_cache_size" in stats
        assert "rag_cache_size" in stats
        assert isinstance(stats["summary_cache_size"], int)
        assert isinstance(stats["rag_cache_size"], int)
