from __future__ import annotations

from typing import Any


class LLMError(RuntimeError):
    """Base runtime error for LLM/provider pipeline failures."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


class LLMTransportError(LLMError):
    """Network or transport-level failure when calling the provider."""


class LLMResponseError(LLMError):
    """Provider returned an invalid or unusable response."""


class LLMConfigurationError(LLMError):
    """Local LLM configuration cannot satisfy the requested call."""


class RetrievalError(LLMError):
    """Knowledge retrieval stage failed."""
