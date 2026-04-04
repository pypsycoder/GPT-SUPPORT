"""
LLM Agent — сборка промптов и вызов GigaChat API.

Функция generate_response:
  1. Выбирает системный промпт (base_system + domain_*)
  2. Собирает messages для API
  3. Получает клиента из пула
  4. Делает запрос
  5. Логирует в llm_request_logs
  6. Возвращает результат
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.errors import LLMError, LLMResponseError, LLMTransportError
from app.llm.pool import pool
from app.llm.router import RouterResult, RequestType
from app.llm.keywords import MEDICATION_KEYWORDS

# Постфикс для кризисных ситуаций — добавляется на уровне кода, не промпта
CRISIS_POSTFIX = (
    "\n\nЕсли тебе сейчас очень плохо — позвони:\n"
    "📞 Телефон доверия: 8-800-2000-122 (бесплатно, круглосуточно)\n"
    "🚑 Скорая помощь: 103"
)

logger = logging.getLogger("gpt-support-llm.agent")


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _build_pipeline_summary(pipeline_diag: dict[str, object]) -> dict[str, object]:
    patient_context = pipeline_diag.get("patient_context", {})
    parser = pipeline_diag.get("parser", {})
    prompt = pipeline_diag.get("prompt", {})
    llm_call = pipeline_diag.get("llm_call", {})
    classify = pipeline_diag.get("classify", {})

    failed_sections = list(patient_context.get("sections_failed", []))
    fallback_points: list[str] = []
    if failed_sections:
        fallback_points.append("patient_context_sections")
    if parser.get("fallback_used"):
        fallback_points.append("parser")
    if patient_context.get("rag", {}).get("error"):
        fallback_points.append("rag")

    total_stage_latency_ms = (
        int(parser.get("latency_ms", 0))
        + int(patient_context.get("total_latency_ms", 0))
        + int(llm_call.get("latency_ms", 0))
    )

    return {
        "request_type": classify.get("request_type"),
        "model_tier": llm_call.get("model_tier"),
        "domain_requested": classify.get("router_domain"),
        "domain_effective": classify.get("effective_domain"),
        "status": llm_call.get("status", "pending"),
        "failure_stage": llm_call.get("failure_stage"),
        "fallback_points": fallback_points,
        "patient_context_failed_sections": failed_sections,
        "rag_hit": bool(patient_context.get("rag", {}).get("hit_count", 0)),
        "rag_error": patient_context.get("rag", {}).get("error"),
        "prompt_chars_total": prompt.get("system_prompt_chars", 0),
        "prompt_tokens_estimate": prompt.get("system_prompt_tokens_estimate", 0),
        "response_chars": llm_call.get("response_chars", 0),
        "tokens_input": llm_call.get("tokens_input", 0),
        "tokens_output": llm_call.get("tokens_output", 0),
        "total_stage_latency_ms": total_stage_latency_ms,
    }


def _format_pipeline_diag_for_log(patient_id: int, pipeline_diag: dict[str, object]) -> str:
    classify = pipeline_diag.get("classify", {})
    patient_context = pipeline_diag.get("patient_context", {})
    rag = patient_context.get("rag", {})
    parser = pipeline_diag.get("parser", {})
    prompt = pipeline_diag.get("prompt", {})
    llm_call = pipeline_diag.get("llm_call", {})
    summary = pipeline_diag.get("summary", {})

    failed_sections = patient_context.get("sections_failed", [])
    fallback_points = summary.get("fallback_points", [])
    included_sections = prompt.get("included_sections", [])

    lines = [
        f"[agent] pipeline patient={patient_id}",
        "  classify:",
        "    "
        f"type={classify.get('request_type')} "
        f"tier={classify.get('model_tier')} "
        f"domain={classify.get('router_domain')} "
        f"effective={classify.get('effective_domain')} "
        f"priority={classify.get('priority')}",
        "  patient_context:",
        "    "
        f"latency_ms={patient_context.get('total_latency_ms', 0)} "
        f"ok={len(patient_context.get('sections_ok', []))} "
        f"failed={len(failed_sections)}",
        "    "
        f"failed_sections={failed_sections if failed_sections else '-'}",
        "  rag:",
        "    "
        f"backend={rag.get('backend')} "
        f"selected={rag.get('backend_selected')} "
        f"hit_count={rag.get('hit_count', 0)} "
        f"candidate_rows={rag.get('candidate_rows', 0)} "
        f"blocker={rag.get('pgvector_blocker')}",
        "    "
        f"embedding_ms={rag.get('embedding_request_ms', 0)} "
        f"search_ms={rag.get('vector_search_ms', 0)} "
        f"progress_ms={rag.get('progress_lookup_ms', 0)} "
        f"total_ms={rag.get('latency_ms', 0)}",
        "  parser:",
        "    "
        f"attempted={parser.get('attempted')} "
        f"succeeded={parser.get('succeeded')} "
        f"fallback={parser.get('fallback_used')} "
        f"mood={parser.get('mood')} "
        f"domain_hints={parser.get('domain_hints') or '-'} "
        f"latency_ms={parser.get('latency_ms', 0)}",
        "  prompt:",
        "    "
        f"system_chars={prompt.get('system_prompt_chars', 0)} "
        f"system_tokens_est={prompt.get('system_prompt_tokens_estimate', 0)} "
        f"context_chars={prompt.get('context_chars', 0)} "
        f"history_messages={prompt.get('history_messages', 0)} "
        f"rag_items={prompt.get('rag_context_items', 0)}",
        "    "
        f"included_sections={included_sections if included_sections else '-'}",
        "  llm_call:",
        "    "
        f"status={llm_call.get('status')} "
        f"account={llm_call.get('account_id')} "
        f"latency_ms={llm_call.get('latency_ms', 0)} "
        f"tokens_in={llm_call.get('tokens_input', 0)} "
        f"tokens_out={llm_call.get('tokens_output', 0)} "
        f"response_chars={llm_call.get('response_chars', 0)}",
        "  summary:",
        "    "
        f"status={summary.get('status')} "
        f"fallbacks={fallback_points if fallback_points else '-'} "
        f"failure_stage={summary.get('failure_stage')} "
        f"total_stage_ms={summary.get('total_stage_latency_ms', 0)}",
    ]
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Постобработка ответов
# ---------------------------------------------------------------------------

_SOFTENER_PHRASES = [
    "но ничего страшного",
    "ничего страшного",
    "не страшно",
]

def _strip_softeners(text: str) -> str:
    """Убирает обесценивающие фразы из ответа модели (только для критичных доменов)."""
    for phrase in _SOFTENER_PHRASES:
        text = re.sub(
            rf',?\s*(но\s+)?{re.escape(phrase)}[,.]?\s*',
            ' ',
            text,
            flags=re.IGNORECASE,
        )
    # Убираем задвоенные пробелы после замены
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()

# ---------------------------------------------------------------------------
# Промпты
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_prompt_cache: dict[str, str] = {}


def load_prompt(filename: str) -> str:
    """
    Читает файл промпта из app/llm/prompts/, кэширует результат.

    Args:
        filename: имя файла (например "base_system.txt")

    Returns:
        Содержимое файла.

    Raises:
        FileNotFoundError: если файл не существует.
    """
    if filename in _prompt_cache:
        return _prompt_cache[filename]

    path = _PROMPTS_DIR / filename
    text = path.read_text(encoding="utf-8").strip()
    _prompt_cache[filename] = text
    return text


def _build_system_prompt(
    domain_hint: str | None,
    *,
    include_support_overlay: bool = False,
) -> str:
    """Объединяет base_system.txt с domain-специфичным промптом и support overlay."""
    base = load_prompt("base_system.txt")
    parts = [base]

    if domain_hint:
        domain_file = f"domain_{domain_hint}.txt"
        try:
            domain_extra = load_prompt(domain_file)
            parts.append(domain_extra)
        except FileNotFoundError:
            logger.debug("[agent] Нет domain-промпта: %s", domain_file)

    if include_support_overlay:
        parts.append(load_prompt("policy_support_overlay.txt"))

    return "\n\n".join(parts)


def _get_support_overlay_reasons(
    router_result: RouterResult,
    *,
    parser_mood: str | None,
    parser_domain_hints: list[str] | None,
) -> list[str]:
    """Определяет, нужен ли emotional-first overlay без смены домена."""
    if router_result.request_type == RequestType.SAFETY:
        return []

    reasons: list[str] = []
    if parser_mood == "bad":
        reasons.append("mood_bad")
    if "emotion" in (parser_domain_hints or []):
        reasons.append("emotion_hint")
    return reasons


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------

async def generate_response(
    patient_id: int,
    user_input: str,
    router_result: RouterResult,
    context: dict,
    db: AsyncSession,
) -> dict:
    """
    Генерирует ответ LLM и логирует запрос в БД.

    Args:
        patient_id:    ID пациента
        user_input:    текст запроса пользователя
        router_result: результат classify_request()
        context:       дополнительный контекст (history и пр., опционально)
        db:            AsyncSession для логирования

    Returns:
        {
          "response": str,
          "tokens_input": int,
          "tokens_output": int,
          "model": str,
          "domain": str | None,
          "response_time_ms": int,
          "account_id": str,
        }
    """
    from app.llm.context_builder import build_context_bundle, format_context_for_llm
    from app.models.llm import LLMRequestLog  # локальный импорт избегает циклов

    pipeline_diag: dict[str, object] = {
        "classify": {
            "request_type": router_result.request_type.value,
            "model_tier": router_result.model_tier.value,
            "router_domain": router_result.domain_hint,
            "effective_domain": router_result.domain_hint,
            "priority": router_result.priority,
            "source_context": list(context.keys()),
        },
        "patient_context": {},
        "parser": {
            "attempted": False,
            "succeeded": False,
            "fallback_used": False,
            "latency_ms": 0,
            "error": None,
            "error_type": None,
            "pending_vitals_count": 0,
            "domain_hints": [],
            "mood": None,
        },
        "prompt": {
            "context_chars": 0,
            "daily_context_chars": 0,
            "history_messages": 0,
            "history_chars": 0,
            "system_prompt_chars": 0,
            "system_prompt_tokens_estimate": 0,
            "user_input_chars": len(user_input),
            "user_input_tokens_estimate": _estimate_text_tokens(user_input),
            "included_sections": [],
            "rag_context_items": 0,
            "support_overlay_applied": False,
            "support_overlay_reasons": [],
        },
        "llm_call": {
            "model_tier": router_result.model_tier.value,
            "account_id": None,
            "latency_ms": 0,
            "status": "pending",
            "failure_stage": None,
            "error": None,
            "error_type": None,
            "response_chars": 0,
            "tokens_input": 0,
            "tokens_output": 0,
        },
    }

    # 1. Собираем данные пациента из БД
    # Для кнопок RAG не нужен — они не несут смысловой нагрузки для поиска по урокам
    rag_query = "" if router_result.request_type == RequestType.QUICK_ACTION else user_input
    context_bundle = await build_context_bundle(patient_id, db, query=rag_query)
    patient_context = context_bundle["context"]
    pipeline_diag["patient_context"] = context_bundle["diagnostics"]
    context_text = format_context_for_llm(patient_context)
    pipeline_diag["prompt"]["context_chars"] = len(context_text)
    pipeline_diag["prompt"]["included_sections"] = [
        name for name, values in patient_context.items()
        if name != "chat_history" and values
    ]
    pipeline_diag["prompt"]["rag_context_items"] = len(patient_context.get("rag_context", []))

    # 1b. Парсим сообщение пациента для извлечения структурированных данных
    _parsed_domain_hints: list[str] = []
    _pending_vitals: list[dict] = []
    parser_started = time.monotonic()
    try:
        if (
            len(user_input) > 30
            and router_result.request_type != RequestType.QUICK_ACTION
        ):
            pipeline_diag["parser"]["attempted"] = True
            from app.llm.parser import parse_patient_message
            parsed = await parse_patient_message(user_input, patient_id)
            logger.info("[agent] parsed: %s", parsed)
            if parsed:
                pipeline_diag["parser"]["succeeded"] = True
                # Витальные НЕ записываем в БД — возвращаем для подтверждения пациентом
                raw_vitals = parsed.get("vitals", [])
                if raw_vitals:
                    from app.llm.parser import normalize_bp, normalize_pulse
                    for v in raw_vitals:
                        vtype = str(v.get("type", "")).upper()
                        value = v.get("value", "")
                        valid = False
                        try:
                            if vtype == "BP":
                                valid = normalize_bp(value) is not None
                            elif vtype == "PULSE":
                                valid = normalize_pulse(value) is not None
                            elif vtype == "WEIGHT":
                                float(str(value).strip())
                                valid = True
                            elif vtype == "WATER":
                                int(float(str(value).strip()))
                                valid = True
                        except (ValueError, AttributeError):
                            pass
                        if valid:
                            _pending_vitals.append({"type": vtype, "value": value})
                        else:
                            logger.warning("[agent] пропускаем невалидный витал %s=%r", vtype, value)
                pipeline_diag["parser"]["pending_vitals_count"] = len(_pending_vitals)
                # Добавляем настроение в контекст пациента
                mood = parsed.get("mood", "unknown")
                pipeline_diag["parser"]["mood"] = mood
                if mood and mood != "unknown":
                    mood_line = f"Настроение: {mood}"
                    context_text = f"{mood_line}\n{context_text}" if context_text else mood_line
                # Подсказки домена для выбора промпта
                _parsed_domain_hints = parsed.get("domain_hints", [])
                pipeline_diag["parser"]["domain_hints"] = list(_parsed_domain_hints)
    except (LLMTransportError, LLMResponseError, ValueError, TypeError, KeyError) as exc:
        pipeline_diag["parser"]["fallback_used"] = True
        pipeline_diag["parser"]["error"] = str(exc)
        pipeline_diag["parser"]["error_type"] = exc.__class__.__name__
        logger.warning("[agent] ошибка парсера, продолжаем без него: %s", exc)
    finally:
        pipeline_diag["parser"]["latency_ms"] = int((time.monotonic() - parser_started) * 1000)

    # 2. Строим системный промпт с контекстом пациента
    effective_domain = router_result.domain_hint or (_parsed_domain_hints[0] if _parsed_domain_hints else None)
    pipeline_diag["classify"]["effective_domain"] = effective_domain
    support_overlay_reasons = _get_support_overlay_reasons(
        router_result,
        parser_mood=pipeline_diag["parser"]["mood"],
        parser_domain_hints=_parsed_domain_hints,
    )
    pipeline_diag["prompt"]["support_overlay_applied"] = bool(support_overlay_reasons)
    pipeline_diag["prompt"]["support_overlay_reasons"] = support_overlay_reasons
    system_prompt = _build_system_prompt(
        effective_domain,
        include_support_overlay=bool(support_overlay_reasons),
    )
    if context_text:
        system_prompt = f"{system_prompt}\n\n{context_text}"
    # Дневной контекст (диализ, лекарства, пропуски) — если передан из chat endpoint
    daily_ctx = context.get("daily_context", "")
    pipeline_diag["prompt"]["daily_context_chars"] = len(daily_ctx)
    if daily_ctx:
        system_prompt = f"{system_prompt}\n\n{daily_ctx}"

    # История: из patient_context (chat_history) или из переданного context
    history: list[dict] = patient_context.get("chat_history") or context.get("history", [])
    pipeline_diag["prompt"]["history_messages"] = len(history)
    pipeline_diag["prompt"]["history_chars"] = sum(len(m.get("content", "")) for m in history)
    messages: list[dict] = [
        *history,
        {"role": "user", "content": user_input},
    ]
    pipeline_diag["prompt"]["system_prompt_chars"] = len(system_prompt)
    pipeline_diag["prompt"]["system_prompt_tokens_estimate"] = _estimate_text_tokens(system_prompt)

    # Получаем клиента из пула
    client = await pool.get_available(router_result.model_tier.value)
    pipeline_diag["llm_call"]["account_id"] = client.account_id

    success = False
    error_message: str | None = None
    response_text = ""
    tokens_in = 0
    tokens_out = 0
    elapsed_ms = 0

    start = time.monotonic()
    try:
        response_text, tokens_in, tokens_out, elapsed_ms = await client.call(
            messages, system_prompt
        )
        pipeline_diag["llm_call"]["latency_ms"] = elapsed_ms
        pipeline_diag["llm_call"]["status"] = "ok"
        pipeline_diag["llm_call"]["response_chars"] = len(response_text)
        pipeline_diag["llm_call"]["tokens_input"] = tokens_in
        pipeline_diag["llm_call"]["tokens_output"] = tokens_out
        success = True
        # Добавляем номера телефонов для кризисных ситуаций
        if router_result.request_type == RequestType.SAFETY:
            response_text += CRISIS_POSTFIX
        # Убираем обесценивающие фразы при пропуске лекарств
        if router_result.domain_hint == "routine":
            lower_input = user_input.lower()
            if any(kw in lower_input for kw in MEDICATION_KEYWORDS):
                response_text = _strip_softeners(response_text)
        from app.llm.pool import MODEL_NAMES as _MODEL_NAMES
        logger.info(
            "[agent] patient=%s domain=%s model=%s\n  Q: %s\n  A: %s",
            patient_id,
            router_result.domain_hint,
            _MODEL_NAMES.get(router_result.model_tier.value, "unknown"),
            user_input[:100],
            response_text[:200],
        )
    except LLMError as exc:
        error_message = str(exc)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        pipeline_diag["llm_call"]["latency_ms"] = elapsed_ms
        pipeline_diag["llm_call"]["status"] = "error"
        pipeline_diag["llm_call"]["failure_stage"] = "llm_call"
        pipeline_diag["llm_call"]["error"] = error_message
        pipeline_diag["llm_call"]["error_type"] = exc.__class__.__name__
        logger.error(
            "[agent] Ошибка LLM patient=%d account=%s: %s",
            patient_id, client.account_id, exc,
        )
        raise

    finally:
        pipeline_diag["summary"] = _build_pipeline_summary(pipeline_diag)
        # Логируем запрос в БД независимо от результата
        from app.llm.pool import MODEL_NAMES
        log = LLMRequestLog(
            patient_id=patient_id,
            account_id=client.account_id,
            model_tier=router_result.model_tier.value,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            response_time_ms=elapsed_ms,
            request_type=router_result.request_type.value,
            success=success,
            error_message=error_message,
            diagnostics_json=pipeline_diag,
        )
        db.add(log)
        await db.flush()

    from app.llm.pool import MODEL_NAMES
    logger.info(_format_pipeline_diag_for_log(patient_id, pipeline_diag))
    return {
        "response": response_text,
        "tokens_input": tokens_in,
        "tokens_output": tokens_out,
        "model": MODEL_NAMES.get(router_result.model_tier.value, "unknown"),
        "domain": router_result.domain_hint,
        "response_time_ms": elapsed_ms,
        "account_id": client.account_id,
        "pending_vitals": _pending_vitals or None,
        "diagnostics": pipeline_diag,
    }
