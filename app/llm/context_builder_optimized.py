"""
Optimized Context Builder - параллельная сборка контекста с кэшированием.

Улучшения:
1. Параллельные запросы к БД через asyncio.gather()
2. Кэширование patient summary (TTL 5 минут)
3. Кэширование RAG результатов (TTL 10 минут)
4. Graceful degradation при ошибках
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.context_builder import (
    _get_recent_vitals,
    _get_medication_adherence,
    _get_sleep_summary,
    _get_active_practices,
    _get_last_scale_scores,
    _get_recent_weight,
    _get_recent_water,
    _get_routine_summary,
    _get_practices_summary,
    _get_chat_history,
    _build_patient_summary_items,
    _build_role_specific_rag_views,
    _get_standalone_psych_support_items,
    _build_rag_grounding_items,
)
from app.llm.errors import RetrievalError

logger = logging.getLogger("gpt-support-llm.context_builder_optimized")


# ============================================================================
# Кэш для patient summary
# ============================================================================

class PatientSummaryCache:
    """Кэш для patient summary с TTL."""
    
    def __init__(self, ttl_seconds: int = 300):  # 5 минут
        self.cache: dict[int, tuple[datetime, list[dict[str, Any]]]] = {}
        self.ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()
    
    async def get(self, patient_id: int) -> list[dict[str, Any]] | None:
        """Получить из кэша, если не истек TTL."""
        async with self._lock:
            if patient_id not in self.cache:
                return None
            
            timestamp, summary = self.cache[patient_id]
            if datetime.now() - timestamp > self.ttl:
                del self.cache[patient_id]
                return None
            
            return summary
    
    async def set(self, patient_id: int, summary: list[dict[str, Any]]):
        """Сохранить в кэш."""
        async with self._lock:
            self.cache[patient_id] = (datetime.now(), summary)
    
    async def invalidate(self, patient_id: int):
        """Инвалидировать кэш для пациента."""
        async with self._lock:
            if patient_id in self.cache:
                del self.cache[patient_id]
    
    async def clear(self):
        """Очистить весь кэш."""
        async with self._lock:
            self.cache.clear()


# Глобальный экземпляр кэша
_summary_cache = PatientSummaryCache()


# ============================================================================
# Кэш для RAG результатов
# ============================================================================

class RAGCache:
    """Кэш для RAG результатов с TTL."""
    
    def __init__(self, ttl_seconds: int = 600):  # 10 минут
        self.cache: dict[tuple[int, str], tuple[datetime, tuple[list[str], dict, list[dict]]]] = {}
        self.ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()
    
    def _make_key(self, patient_id: int, query: str) -> tuple[int, str]:
        """Создать ключ кэша."""
        # Нормализуем query для лучшего кэширования
        normalized = " ".join(query.lower().split())
        return (patient_id, normalized[:100])  # Ограничиваем длину
    
    async def get(self, patient_id: int, query: str) -> tuple[list[str], dict, list[dict]] | None:
        """Получить из кэша, если не истек TTL."""
        key = self._make_key(patient_id, query)
        
        async with self._lock:
            if key not in self.cache:
                return None
            
            timestamp, result = self.cache[key]
            if datetime.now() - timestamp > self.ttl:
                del self.cache[key]
                return None
            
            return result
    
    async def set(self, patient_id: int, query: str, result: tuple[list[str], dict, list[dict]]):
        """Сохранить в кэш."""
        key = self._make_key(patient_id, query)
        
        async with self._lock:
            self.cache[key] = (datetime.now(), result)
    
    async def invalidate(self, patient_id: int):
        """Инвалидировать кэш для пациента."""
        async with self._lock:
            keys_to_delete = [k for k in self.cache.keys() if k[0] == patient_id]
            for key in keys_to_delete:
                del self.cache[key]
    
    async def clear(self):
        """Очистить весь кэш."""
        async with self._lock:
            self.cache.clear()


# Глобальный экземпляр кэша
_rag_cache = RAGCache()


# ============================================================================
# Параллельная сборка контекста
# ============================================================================

async def build_context_bundle_optimized(
    patient_id: int,
    db: AsyncSession,
    query: str = "",
) -> dict:
    """
    Оптимизированная сборка контекста с параллельными запросами и кэшированием.
    
    Улучшения:
    1. Параллельные запросы к БД (10 запросов → 1 batch)
    2. Кэширование patient summary (TTL 5 минут)
    3. Кэширование RAG результатов (TTL 10 минут)
    4. Graceful degradation при ошибках
    
    Args:
        patient_id: ID пациента
        db: AsyncSession
        query: текст запроса для RAG
        
    Returns:
        dict с контекстом и диагностикой
    """
    total_started = time.monotonic()
    
    context: dict = {}
    diagnostics: dict[str, Any] = {
        "patient_id": patient_id,
        "query_length": len(query),
        "total_latency_ms": 0,
        "sections_ok": [],
        "sections_failed": [],
        "section_latency_ms": {},
        "section_item_counts": {},
        "cache_hits": [],
        "cache_misses": [],
        "rag": {
            "attempted": False,
            "skipped_reason": None,
            "backend": None,
            "backend_selected": None,
            "candidate_rows": 0,
            "query_vector_dims": 0,
            "embedding_request_ms": 0,
            "vector_search_ms": 0,
            "progress_lookup_ms": 0,
            "pgvector_extension_installed": False,
            "pgvector_column_present": False,
            "pgvector_index_present": False,
            "pgvector_blocker": None,
            "invalid_embedding_rows": 0,
            "hit_count": 0,
            "error": None,
            "latency_ms": 0,
            "cache_hit": False,
        },
        "summary_items": 0,
        "optimization": {
            "parallel_queries": True,
            "summary_cache_enabled": True,
            "rag_cache_enabled": True,
        },
    }
    
    # ========================================================================
    # Параллельные запросы к БД
    # ========================================================================
    
    sections_to_fetch = {
        "recent_vitals": _get_recent_vitals,
        "medication_adherence": _get_medication_adherence,
        "sleep_summary": _get_sleep_summary,
        "active_practices": _get_active_practices,
        "last_scale_scores": _get_last_scale_scores,
        "recent_weight": _get_recent_weight,
        "recent_water": _get_recent_water,
        "routine_summary": _get_routine_summary,
        "practices_summary": _get_practices_summary,
        "chat_history": _get_chat_history,
    }
    
    parallel_started = time.monotonic()
    
    # Запускаем все запросы параллельно
    results = await asyncio.gather(
        *[fn(patient_id, db) for fn in sections_to_fetch.values()],
        return_exceptions=True
    )
    
    parallel_latency = int((time.monotonic() - parallel_started) * 1000)
    diagnostics["optimization"]["parallel_latency_ms"] = parallel_latency
    
    # Обрабатываем результаты
    for (name, fn), result in zip(sections_to_fetch.items(), results):
        if isinstance(result, Exception):
            logger.warning("[context_optimized] Section '%s' failed: %s", name, result)
            context[name] = []
            diagnostics["sections_failed"].append(name)
        else:
            context[name] = result
            diagnostics["sections_ok"].append(name)
        
        diagnostics["section_item_counts"][name] = len(context[name]) if isinstance(context[name], list) else 0
    
    logger.info(
        "[context_optimized] parallel fetch patient=%d sections_ok=%d sections_failed=%d latency_ms=%d",
        patient_id,
        len(diagnostics["sections_ok"]),
        len(diagnostics["sections_failed"]),
        parallel_latency,
    )
    
    # ========================================================================
    # RAG с кэшированием
    # ========================================================================
    
    context["rag_context"] = []
    context["rag_grounding_items"] = []
    context["psych_support_practice_items"] = []
    context["rag_views"] = {"psych_support": [], "routine": [], "education": []}
    
    # Short natural-language symptom/help queries should still reach RAG.
    if len(query.strip()) >= 10:
        rag_started = time.monotonic()
        diagnostics["rag"]["attempted"] = True
        
        # Проверяем кэш
        cached_rag = await _rag_cache.get(patient_id, query)
        
        if cached_rag is not None:
            # Cache hit
            context["rag_context"], rag_meta, context["rag_grounding_items"] = cached_rag
            diagnostics["rag"]["cache_hit"] = True
            diagnostics["cache_hits"].append("rag")
            
            logger.info(
                "[context_optimized] RAG cache hit patient=%d query_length=%d",
                patient_id,
                len(query),
            )
        else:
            # Cache miss - выполняем RAG
            diagnostics["cache_misses"].append("rag")
            
            try:
                from app.rag.retriever import retrieve_relevant_modules_with_meta
                
                retrieval_result = await retrieve_relevant_modules_with_meta(query, patient_id, db, top_k=5)
                modules = retrieval_result["modules"]
                
                # Строим rag_context
                from app.llm.context_builder import _clip_rag_fragment
                lines = []
                for m in modules:
                    fragment = _clip_rag_fragment(str(m.get("chunk", "")))
                    lines.append(f"Урок «{m['title']}». Релевантный фрагмент: {fragment}")
                
                context["rag_context"] = lines
                
                # Строим grounding items
                context["rag_grounding_items"] = await _build_rag_grounding_items(patient_id, modules, db)
                
                rag_meta = retrieval_result["meta"]
                
                # Сохраняем в кэш
                await _rag_cache.set(
                    patient_id,
                    query,
                    (context["rag_context"], rag_meta, context["rag_grounding_items"])
                )
                
                logger.info(
                    "[context_optimized] RAG cache miss patient=%d query_length=%d hits=%d",
                    patient_id,
                    len(query),
                    len(context["rag_context"]),
                )
            
            except RetrievalError as exc:
                logger.warning("[context_optimized] RAG retriever failed: %s", exc)
                diagnostics["rag"]["error"] = str(exc)
                rag_meta = {}
        
        # Дополнительные RAG данные
        context["psych_support_practice_items"] = await _get_standalone_psych_support_items(
            context["rag_grounding_items"],
            db,
        )
        context["rag_views"] = _build_role_specific_rag_views(
            context["rag_context"],
            context["rag_grounding_items"],
            context["psych_support_practice_items"],
        )
        
        # Диагностика RAG
        if not diagnostics["rag"]["cache_hit"]:
            diagnostics["rag"]["hit_count"] = len(context["rag_context"])
            diagnostics["rag"]["backend"] = rag_meta.get("backend")
            diagnostics["rag"]["backend_selected"] = rag_meta.get("backend_selected")
            diagnostics["rag"]["candidate_rows"] = rag_meta.get("candidate_rows", 0)
            diagnostics["rag"]["query_vector_dims"] = rag_meta.get("query_vector_dims", 0)
            diagnostics["rag"]["embedding_request_ms"] = rag_meta.get("embedding_request_ms", 0)
            diagnostics["rag"]["vector_search_ms"] = rag_meta.get("vector_search_ms", 0)
            diagnostics["rag"]["progress_lookup_ms"] = rag_meta.get("progress_lookup_ms", 0)
            diagnostics["rag"]["pgvector_extension_installed"] = rag_meta.get("pgvector_extension_installed", False)
            diagnostics["rag"]["pgvector_column_present"] = rag_meta.get("pgvector_column_present", False)
            diagnostics["rag"]["pgvector_index_present"] = rag_meta.get("pgvector_index_present", False)
            diagnostics["rag"]["pgvector_blocker"] = rag_meta.get("pgvector_blocker")
            diagnostics["rag"]["invalid_embedding_rows"] = rag_meta.get("invalid_embedding_rows", 0)
        
        diagnostics["rag"]["latency_ms"] = int((time.monotonic() - rag_started) * 1000)
        diagnostics["rag"]["views"] = {
            "psych_support_count": len(context["rag_views"].get("psych_support", [])),
            "routine_count": len(context["rag_views"].get("routine", [])),
            "education_count": len(context["rag_views"].get("education", [])),
        }
    else:
        diagnostics["rag"]["skipped_reason"] = "query_too_short"
        diagnostics["rag"]["views"] = {
            "psych_support_count": 0,
            "routine_count": 0,
            "education_count": 0,
        }
    
    # ========================================================================
    # Patient Summary с кэшированием
    # ========================================================================
    
    summary_started = time.monotonic()
    
    # Проверяем кэш
    cached_summary = await _summary_cache.get(patient_id)
    
    if cached_summary is not None:
        # Cache hit
        context["patient_summary_items"] = cached_summary
        diagnostics["cache_hits"].append("patient_summary")
        
        logger.info(
            "[context_optimized] Summary cache hit patient=%d items=%d",
            patient_id,
            len(cached_summary),
        )
    else:
        # Cache miss - строим summary
        diagnostics["cache_misses"].append("patient_summary")
        
        context["patient_summary_items"] = _build_patient_summary_items(context)
        
        # Сохраняем в кэш
        await _summary_cache.set(patient_id, context["patient_summary_items"])
        
        logger.info(
            "[context_optimized] Summary cache miss patient=%d items=%d",
            patient_id,
            len(context["patient_summary_items"]),
        )
    
    context["patient_summary"] = [str(item["text"]) for item in context["patient_summary_items"]]
    diagnostics["summary_items"] = len(context["patient_summary"])
    diagnostics["optimization"]["summary_latency_ms"] = int((time.monotonic() - summary_started) * 1000)
    
    # ========================================================================
    # Финализация
    # ========================================================================
    
    diagnostics["total_latency_ms"] = int((time.monotonic() - total_started) * 1000)
    
    logger.info(
        "[context_optimized] completed patient=%d total_latency_ms=%d cache_hits=%s",
        patient_id,
        diagnostics["total_latency_ms"],
        diagnostics["cache_hits"],
    )
    
    return {"context": context, "diagnostics": diagnostics}


# ============================================================================
# Утилиты для управления кэшем
# ============================================================================

async def invalidate_patient_cache(patient_id: int):
    """Инвалидировать весь кэш для пациента."""
    await _summary_cache.invalidate(patient_id)
    await _rag_cache.invalidate(patient_id)
    logger.info("[context_optimized] invalidated cache for patient=%d", patient_id)


async def clear_all_caches():
    """Очистить все кэши."""
    await _summary_cache.clear()
    await _rag_cache.clear()
    logger.info("[context_optimized] cleared all caches")


def get_cache_stats() -> dict[str, Any]:
    """Получить статистику кэшей."""
    return {
        "summary_cache_size": len(_summary_cache.cache),
        "rag_cache_size": len(_rag_cache.cache),
    }
