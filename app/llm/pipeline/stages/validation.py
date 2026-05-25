"""
Validation Stage - validation and optional rewrite.
"""

from __future__ import annotations

import logging
import time

from app.llm.agent import _build_rewrite_user_prompt, load_prompt
from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.response_validator import validate_response_for_rewrite
from app.llm.router import RequestType

logger = logging.getLogger("gpt-support-llm.pipeline.validation")

CRISIS_POSTFIX = (
    "\n\nЕсли тебе сейчас очень плохо — позвони:\n"
    "📞 Телефон доверия: 8-800-2000-122 (бесплатно, круглосуточно)\n"
    "🚑 Скорая помощь: 103"
)


class ValidationStage(PipelineStage):
    """Stage 5: validate response drafts from supervisor or legacy orchestration."""

    @property
    def stage_name(self) -> str:
        return "validation"

    async def process(self, context: PipelineContext) -> PipelineContext:
        if context.early_response:
            context.diagnostics["validation"] = {
                "triggered": False,
                "status": "skipped_early_response",
            }
            return context

        started = time.monotonic()
        response_text = self._resolve_response_text(context)
        if not response_text:
            logger.warning("[validation] no response draft, skipping")
            context.diagnostics["validation"] = {"triggered": False, "status": "skipped_no_response"}
            return context

        if context.classification.request_type == RequestType.SAFETY and not response_text.endswith(CRISIS_POSTFIX):
            response_text += CRISIS_POSTFIX

        if context.classification.request_type == RequestType.SAFETY:
            self._store_response_text(context, response_text)
            context.diagnostics["validation"] = {
                "triggered": False,
                "status": "skipped_safety",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            return context

        validation = validate_response_for_rewrite(response_text)
        context.validation_result = validation
        if not validation.triggered:
            self._store_response_text(context, response_text)
            context.diagnostics["validation"] = {
                "triggered": False,
                "status": "passed",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            return context

        if context.orchestration_result is None:
            self._store_response_text(context, response_text)
            context.diagnostics["validation"] = {
                "triggered": True,
                "status": "supervisor_draft_kept",
                "reasons": list(validation.reasons),
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            return context

        try:
            from app.llm.pool import pool

            client = await pool.get_available(context.classification.model_tier.value)
            rewrite_system_prompt = load_prompt("policy_response_rewrite.txt")
            max_attempts = 2

            for attempt in range(max_attempts):
                rewrite_user = _build_rewrite_user_prompt(
                    user_input=context.request.user_input,
                    original_response=response_text,
                    rewrite_reasons=list(validation.reasons),
                )
                rewritten_text, tokens_in, tokens_out, latency_ms = await client.call(
                    [{"role": "user", "content": rewrite_user}],
                    rewrite_system_prompt,
                )
                response_text = rewritten_text.strip()
                context.orchestration_result.final_response = response_text
                context.orchestration_result.tokens_input += tokens_in
                context.orchestration_result.tokens_output += tokens_out
                context.orchestration_result.latency_ms += latency_ms
                post_validation = validate_response_for_rewrite(response_text)
                if not post_validation.triggered:
                    validation = post_validation
                    break
                validation = post_validation

            self._store_response_text(context, response_text)
            context.diagnostics["validation"] = {
                "triggered": True,
                "status": "rewritten",
                "reasons": list(validation.reasons),
                "attempts": attempt + 1,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        except Exception as exc:
            logger.error("[validation] rewrite failed patient=%d: %s", context.request.patient_id, exc)
            self._store_response_text(context, response_text)
            context.diagnostics["validation"] = {
                "triggered": True,
                "status": "rewrite_failed",
                "error": str(exc),
            }

        return context

    def _resolve_response_text(self, context: PipelineContext) -> str | None:
        if context.response_draft:
            return context.response_draft
        if context.orchestration_result:
            return context.orchestration_result.final_response
        return None

    def _store_response_text(self, context: PipelineContext, response_text: str) -> None:
        context.response_draft = response_text
        if context.orchestration_result:
            context.orchestration_result.final_response = response_text
