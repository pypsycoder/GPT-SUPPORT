"""
Main LLM pipeline implementation.
"""

from __future__ import annotations

import logging
import time

from app.llm.pipeline.stages import ClassificationStage, MemoryWriteStage, SupervisorStage
from app.llm.pipeline.stages.boundary_guard import BoundaryGuardStage
from app.llm.pipeline.stages.data_entry import DataEntryStage
from app.llm.pipeline.types import LLMRequest, LLMResponse, PipelineContext
from app.llm.pool import MODEL_NAMES
from app.llm.router import RequestType

logger = logging.getLogger("gpt-support-llm.pipeline")

_SAFETY_POSTFIX = (
    "\n\nЕсли тебе сейчас очень плохо, позвони по номеру 103 или на телефон доверия "
    "8-800-2000-122. Если рядом есть близкий человек, пожалуйста, скажи ему, что тебе нужна помощь прямо сейчас."
)


class LLMPipeline:
    """Current runtime pipeline for LLM requests."""

    def __init__(self):
        self.stages = [
            BoundaryGuardStage(),
            ClassificationStage(),
            # До супервизора: запись показателей моделью не занимается.
            DataEntryStage(),
            SupervisorStage(),
            MemoryWriteStage(),
        ]

    async def process(self, request: LLMRequest) -> LLMResponse:
        pipeline_started = time.monotonic()

        context = PipelineContext(request=request)
        context.diagnostics = {
            "pipeline_started_at": time.time(),
            "stages": [],
        }

        logger.info(
            "[pipeline] started patient=%d input_length=%d source=%s",
            request.patient_id,
            len(request.user_input),
            request.source,
        )

        try:
            for stage in self.stages:
                stage_started = time.monotonic()
                try:
                    context = await stage.process(context)
                    stage_latency = int((time.monotonic() - stage_started) * 1000)
                    context.diagnostics["stages"].append(
                        {
                            "name": stage.stage_name,
                            "status": "ok",
                            "latency_ms": stage_latency,
                        }
                    )
                    logger.debug(
                        "[pipeline] stage=%s completed latency_ms=%d",
                        stage.stage_name,
                        stage_latency,
                    )
                    if context.early_response:
                        logger.info(
                            "[pipeline] early response from %s, skipping remaining stages",
                            context.early_response_source,
                        )
                        break
                except Exception as exc:
                    stage_latency = int((time.monotonic() - stage_started) * 1000)
                    context.diagnostics["stages"].append(
                        {
                            "name": stage.stage_name,
                            "status": "error",
                            "error": str(exc),
                            "error_type": exc.__class__.__name__,
                            "latency_ms": stage_latency,
                        }
                    )
                    logger.error(
                        "[pipeline] stage=%s failed patient=%d: %s",
                        stage.stage_name,
                        request.patient_id,
                        exc,
                    )
                    raise

            response = self._build_response(context, pipeline_started)
        except Exception as exc:
            await self._log_to_database(
                request,
                context,
                error=exc,
                response_time_ms=int((time.monotonic() - pipeline_started) * 1000),
            )
            raise

        await self._log_to_database(request, context, response=response)

        logger.info(
            "[pipeline] completed patient=%d total_latency_ms=%d response_length=%d",
            request.patient_id,
            response.response_time_ms,
            len(response.response),
        )
        return response

    def _build_response(self, context: PipelineContext, pipeline_started: float) -> LLMResponse:
        if context.early_response:
            response_text = context.early_response
            tokens_in = 0
            tokens_out = 0
            account_id = (context.early_response_source or "EARLY_RESPONSE").upper()
            response_source = context.early_response_source or "early_response"
        elif context.response_draft:
            response_text = context.response_draft
            tokens_in = int(context.response_tokens_input or 0)
            tokens_out = int(context.response_tokens_output or 0)
            account_id = context.response_account_id or "SUPERVISOR"
            response_source = "supervisor"
        else:
            response_text = "Извините, произошла ошибка при обработке запроса."
            tokens_in = 0
            tokens_out = 0
            account_id = "ERROR"
            response_source = "error_fallback"

        if (
            context.classification is not None
            and context.classification.request_type is RequestType.SAFETY
            and not context.early_response
            and not context.response_is_fallback_error
            and "8-800-2000-122" not in response_text
        ):
            response_text = f"{response_text.rstrip()}{_SAFETY_POSTFIX}"

        requested_tier = context.classification.model_tier.value if context.classification else "pro"
        actual_tier = context.response_actual_model_tier
        requested_model = MODEL_NAMES.get(requested_tier, "unknown")
        actual_model = MODEL_NAMES.get(actual_tier, requested_model) if actual_tier else requested_model
        total_latency_ms = int((time.monotonic() - pipeline_started) * 1000)

        context.diagnostics["total_latency_ms"] = total_latency_ms
        context.diagnostics["response"] = {
            "source": response_source,
            "account_id": account_id,
        }

        pending_st_memory = list(context.diagnostics.get("memory", {}).get("proposed_st_entries", []))
        pending_lt_memory = list(context.diagnostics.get("memory", {}).get("proposed_lt_entries", []))

        return LLMResponse(
            response=response_text,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            model=actual_model,
            domain=context.classification.domain_hint if context.classification else None,
            response_time_ms=total_latency_ms,
            account_id=account_id,
            requested_model_tier=requested_tier,
            actual_model_tier=actual_tier,
            buttons=list(context.early_response_buttons) if context.early_response_buttons else None,
            pending_vitals=list(context.pending_vitals) or None,
            pending_st_memory=pending_st_memory,
            pending_lt_memory=pending_lt_memory,
            supervisor_state=dict(context.supervisor_state or {}) or None,
            supervisor_state_delta=dict(context.supervisor_turn.state_delta) if context.supervisor_turn else {},
            diagnostics=context.diagnostics,
            education_cta=context.supervisor_turn.education_cta if context.supervisor_turn else None,
        )

    async def _log_to_database(
        self,
        request: LLMRequest,
        context: PipelineContext,
        *,
        response: LLMResponse | None = None,
        error: Exception | None = None,
        response_time_ms: int | None = None,
    ):
        if not request.db:
            return

        try:
            from app.models.llm import LLMRequestLog

            router_result = context.classification or request.router_result
            request_type = router_result.request_type.value if router_result else "unknown"
            model_tier = (
                (response.actual_model_tier or response.requested_model_tier)
                if response is not None
                else (context.response_actual_model_tier or (router_result.model_tier.value if router_result else "unknown"))
            )
            account_id = (
                response.account_id
                if response is not None
                else (
                    context.response_account_id
                    or ((context.early_response_source or "UNKNOWN").upper() if context.early_response else "UNKNOWN")
                )
            )
            log = LLMRequestLog(
                patient_id=request.patient_id,
                # account_id — VARCHAR(20) в БД. Для настоящих LLM-ходов сюда
                # попадает короткий account_id пула ("A1-pro"), но boundary_guard
                # переиспользует это же поле под тег источника раннего ответа
                # (early_response_source.upper()) — и "BOUNDARY_GUARD_MEDICAL_URGENT"
                # (29 симв.) шире колонки. Без среза flush() падает с
                # StringDataRightTruncationError, пойманной здесь try/except-ом,
                # но оставляющей сессию в pending-rollback — следующий
                # session.commit() в вызывающем роутере (app/routers/chat.py)
                # уже не поймать, и пациент в кризисе получает 500 вместо ответа.
                account_id=(account_id or "UNKNOWN")[:20],
                model_tier=model_tier or "unknown",
                tokens_input=response.tokens_input if response is not None else int(context.response_tokens_input or 0),
                tokens_output=response.tokens_output if response is not None else int(context.response_tokens_output or 0),
                response_time_ms=(
                    response.response_time_ms
                    if response is not None
                    else int(response_time_ms or 0)
                ),
                request_type=request_type,
                success=error is None,
                error_message=None if error is None else f"{error.__class__.__name__}: {error}",
            )

            request.db.add(log)
            await request.db.flush()
            logger.debug("[pipeline] logged to database patient=%d", request.patient_id)
        except Exception as exc:
            logger.error("[pipeline] failed to log to database patient=%d: %s", request.patient_id, exc)
