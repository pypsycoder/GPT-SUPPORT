"""
Intake Stage - анализ запроса и определение необходимости кларификации.
"""

from __future__ import annotations

import logging
import time

from app.llm.intake import analyze_help_intake
from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.router import RequestType

logger = logging.getLogger("gpt-support-llm.pipeline.intake")


def _build_clarification_response(*, suggested_question: str | None, primary_problem: str | None) -> str:
    """Строит ответ для кларификации."""
    lead = {
        "sleep_problem": "Похоже, здесь смешались сон и то, как тебе сейчас.",
        "emotional_distress": "Похоже, здесь важно точнее понять, какая помощь нужна прямо сейчас.",
        "low_energy": "Похоже, важно сначала уточнить, какой поддержки тебе сейчас не хватает.",
    }.get(str(primary_problem or ""), "Хочу сначала чуть точнее понять, какая помощь будет тебе полезнее.")
    question = str(suggested_question or "Что сейчас беспокоит тебя больше всего?")
    return f"{lead} {question}"


class IntakeStage(PipelineStage):
    """
    Этап 3: Анализ запроса помощи и кларификация.
    
    Ответственность:
    - Парсить сообщение пациента (настроение, витальные)
    - Анализировать intake (проблема, намерение)
    - Определить необходимость кларификации
    - Применить ST-memory для коротких follow-up
    """
    
    @property
    def stage_name(self) -> str:
        return "intake"
    
    async def process(self, context: PipelineContext) -> PipelineContext:
        if context.supervisor_turn is not None:
            context.diagnostics["parser"] = {
                "attempted": False,
                "succeeded": False,
                "skipped": True,
                "reason": "supervisor_turn",
            }
            context.diagnostics["intake"] = {"skipped": True, "reason": "supervisor_turn"}
            return context

        started = time.monotonic()
        
        # Парсинг сообщения (если нужен)
        parser_mood = None
        parser_domain_hints = []
        
        if (
            len(context.request.user_input) > 30
            and context.classification.request_type != RequestType.QUICK_ACTION
        ):
            try:
                from app.llm.parser import parse_patient_message
                parsed = await parse_patient_message(context.request.user_input, context.request.patient_id)
                if parsed:
                    parser_mood = parsed.get("mood", "unknown")
                    parser_domain_hints = parsed.get("domain_hints", [])
                    context.parser_result = parsed
                    logger.info("[intake] parsed mood=%s hints=%s", parser_mood, parser_domain_hints)
            except Exception as exc:
                logger.warning("[intake] parser failed: %s", exc)
        
        # Intake анализ
        context.intake_result = analyze_help_intake(
            user_input=context.request.user_input,
            router_result=context.classification,
            parser_mood=parser_mood,
            parser_domain_hints=parser_domain_hints,
        )
        
        # Проверка необходимости кларификации
        if (
            context.intake_result.is_help_request
            and context.intake_result.clarification_needed
            and context.classification.request_type != RequestType.SAFETY
        ):
            context.should_skip_orchestration = True
            context.early_response = _build_clarification_response(
                suggested_question=context.intake_result.suggested_question,
                primary_problem=context.intake_result.primary_problem,
            )
            context.early_response_source = "clarifier"
            
            logger.info(
                "[intake] clarification needed patient=%d problem=%s",
                context.request.patient_id,
                context.intake_result.primary_problem,
            )
        
        # Диагностика
        context.diagnostics["parser"] = {
            "attempted": bool(context.parser_result),
            "succeeded": bool(context.parser_result),
            "mood": parser_mood,
            "domain_hints": parser_domain_hints,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
        context.diagnostics["intake"] = context.intake_result.to_dict() if context.intake_result else {}
        
        return context
