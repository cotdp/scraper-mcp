"""MCP server for context-efficient web scraping functionality."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from scraper_mcp.admin.router import (
    api_cache_clear,
    api_config_get,
    api_config_update,
    api_stats,
    health_check,
)
from scraper_mcp.dashboard.router import dashboard as dashboard_view
from scraper_mcp.tools.router import register_cache_tools, register_scraping_tools

# Configuration: Enable cache management tools via environment variable
# Set ENABLE_CACHE_TOOLS=true to expose cache_stats, cache_clear_expired, and cache_clear_all
ENABLE_CACHE_TOOLS = os.getenv("ENABLE_CACHE_TOOLS", "false").lower() in ("true", "1", "yes")

# Create MCP server with stateless mode enabled
# Stateless mode auto-creates sessions for unknown session IDs, making the server
# resilient to restarts and eliminating "No valid session ID" errors
mcp = FastMCP(
    "Scraper MCP",
    instructions=(
        "A web scraping MCP server that provides efficient webpage scraping tools. "
        "Supports scraping HTML content, converting to markdown, extracting text, "
        "and extracting links from webpages."
    ),
    stateless_http=True,  # Accept requests without requiring initialize handshake
)


# Register MCP tools
register_scraping_tools(mcp)

# Register optional cache management tools
if ENABLE_CACHE_TOOLS:
    register_cache_tools(mcp)


# Register admin API routes
mcp.custom_route("/healthz", methods=["GET"])(health_check)
mcp.custom_route("/api/stats", methods=["GET"])(api_stats)
mcp.custom_route("/api/cache/clear", methods=["POST"])(api_cache_clear)
mcp.custom_route("/api/config", methods=["GET"])(api_config_get)
mcp.custom_route("/api/config", methods=["POST"])(api_config_update)

# Register dashboard route
mcp.custom_route("/", methods=["GET"])(dashboard_view)


def run_server(transport: str = "streamable-http", host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the MCP server.

    Args:
        transport: Transport type ('streamable-http' or 'sse')
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8000)
    """
    # Configure host and port via settings
    mcp.settings.host = host
    mcp.settings.port = port

    # Run server with specified transport
    mcp.run(transport=transport)


if __name__ == "__main__":
    run_server()
