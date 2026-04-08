from __future__ import annotations


class LLMError(RuntimeError):
    """Base runtime error for LLM/provider pipeline failures."""


class LLMTransportError(LLMError):
    """Network or transport-level failure when calling the provider."""


class LLMResponseError(LLMError):
    """Provider returned an invalid or unusable response."""


class LLMConfigurationError(LLMError):
    """Local LLM configuration cannot satisfy the requested call."""


class RetrievalError(LLMError):
    """Knowledge retrieval stage failed."""
