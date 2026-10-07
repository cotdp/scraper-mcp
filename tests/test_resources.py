"""Tests for MCP resources."""

from __future__ import annotations

import json
from collections.abc import Callable
from unittest.mock import Mock

from scraper_mcp.metrics import ServerMetrics
from scraper_mcp.providers.base import ScrapeResult
from scraper_mcp.resources.cache import register_cache_resources
from scraper_mcp.resources.server_info import register_server_resources


class _ResourceRegistry:
    """Minimal resource decorator used to capture registered handlers."""

    def __init__(self) -> None:
        self.handlers: dict[str, Callable[..., str]] = {}

    def resource(self, uri: str) -> Callable[[Callable[..., str]], Callable[..., str]]:
        def register(handler: Callable[..., str]) -> Callable[..., str]:
            self.handlers[uri] = handler
            return handler

        return register


def test_server_resources_use_startup_perplexity_availability(monkeypatch) -> None:
    """Runtime credentials must not advertise tools omitted during startup."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "runtime-key")
    monkeypatch.setenv("PERPLEXITY_PROVIDER", "perplexity")

    registry = _ResourceRegistry()
    register_server_resources(registry, perplexity_tools_available=False)  # type: ignore[arg-type]

    info = json.loads(registry.handlers["server://info"]())
    tools = json.loads(registry.handlers["server://tools"]())

    assert "perplexity" not in info["capabilities"]
    assert "perplexity" not in {tool["name"] for tool in tools}
    assert "perplexity_reason" not in {tool["name"] for tool in tools}


def test_cache_resources_serialize_scrape_results(monkeypatch) -> None:
    """Cache resources expose the ScrapeResult objects stored by RequestsProvider."""
    metrics = ServerMetrics()
    request = metrics.record_request(
        url="https://example.com",
        success=True,
        status_code=200,
        cache_key="cache-key",
    )
    cached_result = ScrapeResult(
        url="https://example.com",
        content="cached body",
        status_code=200,
        content_type="text/html",
        metadata={"attempts": 1},
    )
    cache_manager = Mock()
    cache_manager.get.return_value = cached_result

    monkeypatch.setattr("scraper_mcp.resources.cache.get_metrics", lambda: metrics)
    monkeypatch.setattr("scraper_mcp.resources.cache.get_cache_manager", lambda: cache_manager)

    registry = _ResourceRegistry()
    register_cache_resources(registry)  # type: ignore[arg-type]

    details = json.loads(registry.handlers["cache://request/{request_id}"](request.request_id))
    content = registry.handlers["cache://request/{request_id}/content"](request.request_id)
    metadata = json.loads(
        registry.handlers["cache://request/{request_id}/metadata"](request.request_id)
    )

    assert details["cached_content"] == {
        "url": "https://example.com",
        "content": "cached body",
        "status_code": 200,
        "content_type": "text/html",
        "metadata": {"attempts": 1},
    }
    assert content == "cached body"
    assert metadata["cached_metadata"] == {"attempts": 1}
