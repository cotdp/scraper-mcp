"""Resource registration for MCP server."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scraper_mcp.resources.cache import register_cache_resources
from scraper_mcp.resources.config import register_config_resources
from scraper_mcp.resources.server_info import register_server_resources
from scraper_mcp.services.perplexity_service import PerplexityService

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_resources(
    mcp: FastMCP,
    *,
    perplexity_tools_available: bool | None = None,
) -> None:
    """Register all MCP resources on the server.

    Resources provide read-only data access via URI-based addressing.
    They are analogous to GET endpoints in REST APIs.

    Args:
        mcp: The FastMCP server instance
        perplexity_tools_available: Whether Perplexity tools were registered at startup
    """
    if perplexity_tools_available is None:
        perplexity_tools_available = PerplexityService.is_available()

    # Cache resources: cache://stats, cache://requests, cache://request/{id}
    register_cache_resources(mcp)

    # Config resources: config://current, config://defaults, config://scraping, config://cache
    register_config_resources(mcp)

    # Server resources: server://info, server://metrics, server://tools
    register_server_resources(
        mcp,
        perplexity_tools_available=perplexity_tools_available,
    )
