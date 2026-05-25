from __future__ import annotations

API_PREFIX = "/api"
API_V1_PREFIX = f"{API_PREFIX}/v1"


def api_path(versioned_path: str, *, legacy: bool = False) -> str:
    """Build an API mount prefix from a path relative to /api or /api/v1."""
    normalized = versioned_path if versioned_path.startswith("/") else f"/{versioned_path}"
    base = API_PREFIX if legacy else API_V1_PREFIX
    return f"{base}{normalized}"
