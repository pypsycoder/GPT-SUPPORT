"""Compatibility shim for legacy API exception registration imports."""

from __future__ import annotations

from fastapi import FastAPI


def register_api_exception_handlers(_app: FastAPI) -> None:
    """Keep legacy tests/imports working.

    The main application currently relies on built-in exception behavior, while
    some older researcher tests still import this helper directly.
    """

    return None
