"""
Main LLM pipeline implementation.
"""

from __future__ import annotations

import logging
import time

from app.llm.pipeline.stages import ClassificationStage, MemoryWriteStage, SupervisorStage
from app.llm.pipeline.stages.boundary_guard import BoundaryGuardStage
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
        await self._log_to_database(request, response, context)

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
            pending_vitals=None,
            pending_st_memory=pending_st_memory,
            pending_lt_memory=pending_lt_memory,
            supervisor_state=dict(context.supervisor_state or {}) or None,
            supervisor_state_delta=dict(context.supervisor_turn.state_delta) if context.supervisor_turn else {},
            diagnostics=context.diagnostics,
        )

    async def _log_to_database(self, request: LLMRequest, response: LLMResponse, context: PipelineContext):
        if not request.db:
            return

        try:
            from app.models.llm import LLMRequestLog

            log = LLMRequestLog(
                patient_id=request.patient_id,
                account_id=response.account_id or "UNKNOWN",
                model_tier=response.actual_model_tier or response.requested_model_tier,
                tokens_input=response.tokens_input,
                tokens_output=response.tokens_output,
                response_time_ms=response.response_time_ms,
                request_type=context.classification.request_type.value if context.classification else "unknown",
                success=True,
                error_message=None,
            )

            request.db.add(log)
            await request.db.flush()
            logger.debug("[pipeline] logged to database patient=%d", request.patient_id)
        except Exception as exc:
            logger.error("[pipeline] failed to log to database patient=%d: %s", request.patient_id, exc)
