from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.llm import pool as pool_module
from app.llm.errors import LLMConfigurationError, LLMTransportError


def test_get_ssl_verify_defaults_to_secure(monkeypatch):
    monkeypatch.delenv("GIGACHAT_CERT_PATH", raising=False)
    monkeypatch.delenv("GIGACHAT_ALLOW_INSECURE_SSL", raising=False)

    assert pool_module._get_ssl_verify() is True


def test_get_ssl_verify_uses_explicit_cert_path(monkeypatch, tmp_path: Path):
    cert_path = tmp_path / "gigachat-ca.pem"
    cert_path.write_text("fake-cert", encoding="utf-8")
    monkeypatch.setenv("GIGACHAT_CERT_PATH", str(cert_path))
    monkeypatch.delenv("GIGACHAT_ALLOW_INSECURE_SSL", raising=False)

    assert pool_module._get_ssl_verify() == str(cert_path)


def test_get_ssl_verify_allows_insecure_only_when_enabled(monkeypatch):
    monkeypatch.delenv("GIGACHAT_CERT_PATH", raising=False)
    monkeypatch.setenv("GIGACHAT_ALLOW_INSECURE_SSL", "true")

    assert pool_module._get_ssl_verify() is False


def test_safe_response_excerpt_redacts_tokens():
    excerpt = pool_module._safe_response_excerpt(
        '{"access_token":"secret","refresh_token":"another","token":"short","detail":"keep"}'
    )

    assert "secret" not in excerpt
    assert "another" not in excerpt
    assert "short" not in excerpt
    assert "<redacted>" in excerpt
    assert "keep" in excerpt


def test_normalize_httpx_error_marks_ssl_failures_as_configuration():
    exc = httpx.ConnectError(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain"
    )

    normalized = pool_module._normalize_httpx_error(exc)

    assert isinstance(normalized, LLMConfigurationError)
    assert "GIGACHAT_ALLOW_INSECURE_SSL=true" in str(normalized)


def test_normalize_httpx_error_marks_other_transport_failures_as_transport():
    exc = httpx.ConnectError("network unreachable")

    normalized = pool_module._normalize_httpx_error(exc)

    assert isinstance(normalized, LLMTransportError)
    assert "transport error" in str(normalized)
