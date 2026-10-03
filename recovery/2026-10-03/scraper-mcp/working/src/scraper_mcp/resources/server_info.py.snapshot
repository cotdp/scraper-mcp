"""Server information resources for MCP server."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from scraper_mcp.admin.service import get_stats
from scraper_mcp.metrics import get_metrics

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


# Server version - should match pyproject.toml
SERVER_VERSION = "0.4.0"


def register_server_resources(mcp: FastMCP, *, perplexity_tools_available: bool) -> None:
    """Register server information resources on the MCP server.

    Args:
        mcp: The FastMCP server instance
        perplexity_tools_available: Whether Perplexity tools were registered at startup
    """

    @mcp.resource("server://info")
    def server_info_resource() -> str:
        """Server information including version, uptime, and capabilities."""
        metrics = get_metrics()

        # Determine enabled capabilities
        capabilities = ["scraping", "caching"]
        if perplexity_tools_available:
            capabilities.append("perplexity")
        if os.getenv("ENABLE_CACHE_TOOLS", "").lower() == "true":
            capabilities.append("cache_tools")
        if os.getenv("DISABLE_RESOURCES", "").lower() != "true":
            capabilities.append("resources")
        if os.getenv("DISABLE_PROMPTS", "").lower() != "true":
            capabilities.append("prompts")

        info = {
            "name": "Scraper MCP",
            "version": SERVER_VERSION,
            "description": "Context-optimized MCP server for web scraping",
            "capabilities": capabilities,
            "uptime": {
                "seconds": metrics.get_uptime_seconds(),
                "formatted": metrics._format_uptime(metrics.get_uptime_seconds()),
            },
            "start_time": metrics.start_time.isoformat(),
        }
        return json.dumps(info, indent=2)

    @mcp.resource("server://metrics")
    def server_metrics_resource() -> str:
        """Request metrics and statistics.

        Includes total requests, success rates, retries, and timing data.
        """
        stats = get_stats()
        return json.dumps(stats, indent=2)

    @mcp.resource("server://tools")
    def server_tools_resource() -> str:
        """List of available MCP tools with descriptions.

        Shows all registered tools and their purposes.
        """
        tools = [
            {
                "name": "scrape_url",
                "description": "Scrape URLs and convert HTML to markdown (best for LLMs)",
                "parameters": ["urls", "timeout", "max_retries", "strip_tags", "css_selector"],
            },
            {
                "name": "scrape_url_html",
                "description": "Scrape raw HTML content from URLs",
                "parameters": ["urls", "timeout", "max_retries", "css_selector", "include_headers"],
            },
            {
                "name": "scrape_url_text",
                "description": "Scrape URLs and extract plain text",
                "parameters": ["urls", "timeout", "max_retries", "strip_tags", "css_selector"],
            },
            {
                "name": "scrape_extract_links",
                "description": "Extract all links from URLs with metadata",
                "parameters": ["urls", "timeout", "max_retries", "css_selector"],
            },
        ]

        # Add Perplexity tools if available (direct API or via OpenRouter)
        if perplexity_tools_available:
            tools.extend(
                [
                    {
                        "name": "perplexity",
                        "description": "AI-powered web search with citations",
                        "parameters": ["messages", "model", "temperature", "max_tokens"],
                    },
                    {
                        "name": "perplexity_reason",
                        "description": "Complex reasoning tasks with step-by-step analysis",
                        "parameters": ["query", "temperature", "max_tokens"],
                    },
                ]
            )

        # Add cache tools if enabled
        if os.getenv("ENABLE_CACHE_TOOLS", "").lower() == "true":
            tools.extend(
                [
                    {
                        "name": "cache_stats",
                        "description": "Get cache statistics",
                        "parameters": [],
                    },
                    {
                        "name": "cache_clear_expired",
                        "description": "Clear expired cache entries",
                        "parameters": [],
                    },
                    {
                        "name": "cache_clear_all",
                        "description": "Clear all cache entries",
                        "parameters": [],
                    },
                ]
            )

        return json.dumps(tools, indent=2)
