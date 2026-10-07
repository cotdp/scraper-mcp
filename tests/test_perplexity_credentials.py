"""Credentials must not escape through Perplexity/OpenRouter error responses or metrics."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import quote

import pytest
import requests

from scraper_mcp.models.perplexity import PerplexityResponse
from scraper_mcp.services.perplexity_service import PerplexityService

OPENROUTER_KEY = "sk-or-fictional-key-3141"
PROXY_USER = "example-user"
PROXY_PASSWORD = "fictional-proxy-password-7924"
PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASSWORD}@proxy.example.invalid:8080"
SECRETS = (OPENROUTER_KEY, PROXY_USER, PROXY_PASSWORD)


def _get_config(key: str, default: Any = None) -> Any:
    return {
        "openrouter_api_key": OPENROUTER_KEY,
        "perplexity_provider": "openrouter",
        "perplexity_enabled_models": ["sonar"],
    }.get(key, default)


@pytest.fixture
def record_request() -> Iterator[MagicMock]:
    with (
        patch.dict(os.environ, {"HTTPS_PROXY": PROXY_URL}, clear=True),
        patch("scraper_mcp.services.perplexity_service.get_config", side_effect=_get_config),
        patch("scraper_mcp.services.perplexity_service.record_request") as recorded,
    ):
        yield recorded


async def _chat_with(post: Mock) -> PerplexityResponse:
    with patch("scraper_mcp.services.perplexity_service.requests.post", post):
        return await PerplexityService().chat(messages=[{"role": "user", "content": "hi"}])


def _assert_no_secrets(response: PerplexityResponse, recorded: MagicMock) -> None:
    observable = response.model_dump_json() + repr(recorded.call_args_list)
    for secret in SECRETS:
        for form in (secret, quote(secret, safe="")):
            assert form not in observable


def _response(status_code: int, text: str = "", payload: object | None = None) -> Mock:
    response = Mock(status_code=status_code, text=text)
    response.json = Mock(return_value=payload)
    return response


@pytest.mark.asyncio
async def test_transport_error_text_is_not_reflected(record_request: MagicMock) -> None:
    error = requests.exceptions.ProxyError(f"Unable to connect to proxy {PROXY_URL}")

    response = await _chat_with(Mock(side_effect=error))

    _assert_no_secrets(response, record_request)
    assert response.metadata["error"] == "OpenRouter connection error: ProxyError"
    assert record_request.call_args.kwargs["status_code"] == 502


@pytest.mark.asyncio
async def test_upstream_error_body_is_redacted(record_request: MagicMock) -> None:
    body = f"invalid key {OPENROUTER_KEY} via {PROXY_URL} ({quote(PROXY_PASSWORD)})"

    response = await _chat_with(Mock(return_value=_response(401, text=body)))

    _assert_no_secrets(response, record_request)
    assert response.metadata["error"].startswith("OpenRouter API error (HTTP 401): invalid key")
    assert record_request.call_args.kwargs["status_code"] == 401


@pytest.mark.asyncio
async def test_error_payload_on_200_is_redacted(record_request: MagicMock) -> None:
    payload = {"error": {"message": f"key {OPENROUTER_KEY} lacks credit", "code": 402}}

    response = await _chat_with(Mock(return_value=_response(200, payload=payload)))

    _assert_no_secrets(response, record_request)
    assert response.metadata["error"] == "OpenRouter error: key [REDACTED] lacks credit"


@pytest.mark.asyncio
async def test_unexpected_error_reports_type_only(record_request: MagicMock) -> None:
    response = await _chat_with(Mock(side_effect=RuntimeError(f"pool for {PROXY_URL}")))

    _assert_no_secrets(response, record_request)
    assert response.metadata["error"] == "Unexpected error: RuntimeError"
    assert record_request.call_args.kwargs["error"] == "Unexpected error: RuntimeError"
