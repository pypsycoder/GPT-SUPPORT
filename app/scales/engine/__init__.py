"""Questionnaire engine package.

Exposes helper functions to run questionnaire workflows independent
from any specific client (Telegram, web, etc.).
"""

from .questionnaire_service import (  # noqa: F401
    start_questionnaire_for_user,
    process_answer,
    compute_scores,
    interpret_scores,
    build_result,
)

