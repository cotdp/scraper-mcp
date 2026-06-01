"""Configuration resources for MCP server."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scraper_mcp.admin.service import (
    DEFAULT_CONCURRENCY,
    get_current_config,
)
from scraper_mcp.models.perplexity import (
    DEFAULT_ENABLED_PERPLEXITY_MODELS,
    PERPLEXITY_MODELS,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


# Default configuration values
DEFAULT_CONFIG = {
    "concurrency": DEFAULT_CONCURRENCY,
    "default_timeout": 30,
    "default_max_retries": 3,
    "cache_ttl_default": 3600,
    "cache_ttl_static": 86400,
    "cache_ttl_realtime": 300,
    "proxy_enabled": False,
    "http_proxy": "",
    "https_proxy": "",
    "no_proxy": "",
    "verify_ssl": False,
    "perplexity_api_key": "",
    "perplexity_enabled_models": list(DEFAULT_ENABLED_PERPLEXITY_MODELS),
}


def register_config_resources(mcp: FastMCP) -> None:
    """Register configuration resources on the MCP server.

    Args:
        mcp: The FastMCP server instance
    """

    @mcp.resource("config://current")
    def config_current_resource() -> str:
        """Current runtime configuration including all active settings."""
        config_data = get_current_config()
        return json.dumps(config_data, indent=2)

    @mcp.resource("config://defaults")
    def config_defaults_resource() -> str:
        """Default configuration values before any runtime overrides."""
        return json.dumps(DEFAULT_CONFIG, indent=2)

    @mcp.resource("config://scraping")
    def config_scraping_resource() -> str:
        """Scraping-specific configuration settings.

        Includes timeout, retry, and concurrency settings.
        """
        config_data = get_current_config()
        config = config_data.get("config", {})

        scraping_config = {
            "timeout": config.get("default_timeout", 30),
            "max_retries": config.get("default_max_retries", 3),
            "concurrency": config.get("concurrency", DEFAULT_CONCURRENCY),
            "verify_ssl": config.get("verify_ssl", False),
        }
        return json.dumps(scraping_config, indent=2)

    @mcp.resource("config://cache")
    def config_cache_resource() -> str:
        """Cache-specific configuration settings.

        Includes TTL settings for different content types.
        """
        config_data = get_current_config()
        config = config_data.get("config", {})

        cache_config = {
            "ttl_default": config.get("cache_ttl_default", 3600),
            "ttl_realtime": config.get("cache_ttl_realtime", 300),
            "ttl_static": config.get("cache_ttl_static", 86400),
            "description": {
                "ttl_default": "Default cache duration for most content (1 hour)",
                "ttl_realtime": "Cache duration for API/live data (5 minutes)",
                "ttl_static": "Cache duration for static content (24 hours)",
            },
        }
        return json.dumps(cache_config, indent=2)

    @mcp.resource("config://perplexity")
    def config_perplexity_resource() -> str:
        """Perplexity-specific configuration settings.

        Reports which models are enabled (opt-in), the full list of available
        models, and whether an API key is configured. The API key itself is
        masked and never exposed.
        """
        config_data = get_current_config()
        config = config_data.get("config", {})

        perplexity_config = {
            "api_key": config.get("perplexity_api_key", ""),  # already masked
            "api_key_configured": bool(config.get("perplexity_api_key")),
            "enabled_models": config.get(
                "perplexity_enabled_models", list(DEFAULT_ENABLED_PERPLEXITY_MODELS)
            ),
            "available_models": list(PERPLEXITY_MODELS),
            "description": {
                "enabled_models": "Models that may be used. Others are rejected (opt-in).",
                "default": f"Only {list(DEFAULT_ENABLED_PERPLEXITY_MODELS)} enabled by default.",
            },
        }
        return json.dumps(perplexity_config, indent=2)
