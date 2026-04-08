"""
Orchestration Stage - legacy orchestration bridge.
"""

from __future__ import annotations

import logging
import time

from app.llm.orchestration import run_full_llm_orchestration, run_specialist_grounding_probe
from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.pool import MODEL_NAMES, pool
from app.llm.router import RequestType

logger = logging.getLogger("gpt-support-llm.pipeline.orchestration")


class OrchestrationStage(PipelineStage):
    """Stage 4: legacy LLM orchestration, skipped for supervisor turns."""

    @property
    def stage_name(self) -> str:
        return "orchestration"

    async def process(self, context: PipelineContext) -> PipelineContext:
        if context.supervisor_turn is not None:
            context.diagnostics["orchestration"] = {
                "enabled": False,
                "skipped": True,
                "reason": "supervisor_turn",
            }
            return context

        if context.should_skip_orchestration:
            return context

        started = time.monotonic()
        requested_model_tier = context.classification.model_tier.value
        requested_model_name = MODEL_NAMES.get(requested_model_tier, "unknown")

        try:
            client = await pool.get_available(requested_model_tier)
            actual_model_tier = client.model_tier
            actual_model_name = MODEL_NAMES.get(actual_model_tier, "unknown")

            orchestration_mode = context.request.orchestration_mode
            use_specialist_probe = (
                orchestration_mode == "specialist_rag"
                and context.classification.request_type != RequestType.SAFETY
            )
            use_llm_full = (
                orchestration_mode == "llm_full"
                and context.classification.request_type != RequestType.SAFETY
            )

            if use_llm_full:
                result = await run_full_llm_orchestration(
                    client=client,
                    user_input=context.request.user_input,
                    router_result=context.classification,
                    parser_mood=context.diagnostics.get("parser", {}).get("mood"),
                    parser_domain_hints=context.diagnostics.get("parser", {}).get("domain_hints", []),
                    patient_summary_prompt=context.patient_context.get("patient_summary_prompt", []),
                    patient_summary_views=context.patient_context.get("patient_summary_views", {}),
                    rag_context=context.patient_context.get("rag_context", []),
                    rag_views=context.patient_context.get("rag_views", {}),
                    rag_grounding_items=context.patient_context.get("rag_grounding_items", []),
                )
                context.orchestration_result = result

            elif use_specialist_probe:
                result = await run_specialist_grounding_probe(
                    client=client,
                    user_input=context.request.user_input,
                    router_result=context.classification,
                    parser_mood=context.diagnostics.get("parser", {}).get("mood"),
                    parser_domain_hints=context.diagnostics.get("parser", {}).get("domain_hints", []),
                    patient_summary_prompt=context.patient_context.get("patient_summary_prompt", []),
                    patient_summary_views=context.patient_context.get("patient_summary_views", {}),
                    rag_context=context.patient_context.get("rag_context", []),
                    rag_views=context.patient_context.get("rag_views", {}),
                    rag_grounding_items=context.patient_context.get("rag_grounding_items", []),
                    selected_agents=["psych_support", "education", "routine"],
                )
                context.orchestration_result = result
            else:
                result = await run_full_llm_orchestration(
                    client=client,
                    user_input=context.request.user_input,
                    router_result=context.classification,
                    parser_mood=context.diagnostics.get("parser", {}).get("mood"),
                    parser_domain_hints=context.diagnostics.get("parser", {}).get("domain_hints", []),
                    patient_summary_prompt=context.patient_context.get("patient_summary_prompt", []),
                    patient_summary_views=context.patient_context.get("patient_summary_views", {}),
                    rag_context=context.patient_context.get("rag_context", []),
                    rag_views=context.patient_context.get("rag_views", {}),
                    rag_grounding_items=context.patient_context.get("rag_grounding_items", []),
                )
                context.orchestration_result = result

            context.diagnostics["orchestration"] = {
                "enabled": True,
                "mode": orchestration_mode,
                "requested_model_tier": requested_model_tier,
                "requested_model": requested_model_name,
                "actual_model_tier": actual_model_tier,
                "actual_model": actual_model_name,
                "account_id": client.account_id,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        except Exception as exc:
            logger.error("[orchestration] failed patient=%d: %s", context.request.patient_id, exc)
            context.diagnostics["orchestration"] = {
                "enabled": False,
                "error": str(exc),
                "error_type": exc.__class__.__name__,
            }
            raise

        return context
