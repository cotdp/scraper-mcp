"""MCP server for context-efficient web scraping functionality."""

from __future__ import annotations

import json
import os
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from scraper_mcp.admin.router import (
    api_cache_clear,
    api_config_get,
    api_config_update,
    api_request_details,
    api_stats,
    health_check,
)
from scraper_mcp.dashboard.router import dashboard as dashboard_view
from scraper_mcp.services.perplexity_service import PerplexityService
from scraper_mcp.tools.router import (
    register_cache_tools,
    register_perplexity_tools,
    register_scraping_tools,
)

# Configuration: Enable cache management tools via environment variable
# Set ENABLE_CACHE_TOOLS=true to expose cache_stats, cache_clear_expired, and cache_clear_all
ENABLE_CACHE_TOOLS = os.getenv("ENABLE_CACHE_TOOLS", "false").lower() in ("true", "1", "yes")

# Configuration: Enable resources/prompts via environment variables
# Resources and prompts are DISABLED by default to reduce context overhead
# Set ENABLE_RESOURCES=true or ENABLE_PROMPTS=true to enable them
ENABLE_RESOURCES_ENV = os.getenv("ENABLE_RESOURCES", "false").lower() in ("true", "1", "yes")
ENABLE_PROMPTS_ENV = os.getenv("ENABLE_PROMPTS", "false").lower() in ("true", "1", "yes")

Transport = Literal["stdio", "sse", "streamable-http"]


# Default allowed hosts/origins for Docker environments
# These are added automatically so Docker users don't need extra configuration
DEFAULT_ALLOWED_HOSTS = [
    "localhost",
    "localhost:8000",
    "127.0.0.1",
    "127.0.0.1:8000",
    "host.docker.internal",  # Docker Desktop (Mac/Windows) host access
    "host.docker.internal:8000",  # Host header includes port
]
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://host.docker.internal:8000",  # Docker Desktop (Mac/Windows) host access
]


def _get_transport_security_settings() -> TransportSecuritySettings:
    """Read transport security settings from environment variables.

    MCP 1.24+ enables DNS rebinding protection by default. This function reads
    FASTMCP_TRANSPORT_SECURITY__ALLOWED_HOSTS and FASTMCP_TRANSPORT_SECURITY__ALLOWED_ORIGINS
    environment variables to configure allowed hosts and origins.

    Default hosts include localhost, 127.0.0.1, and host.docker.internal for Docker support.

    Returns:
        TransportSecuritySettings with configured or default allowed hosts/origins
    """
    allowed_hosts_env = os.getenv("FASTMCP_TRANSPORT_SECURITY__ALLOWED_HOSTS")
    allowed_origins_env = os.getenv("FASTMCP_TRANSPORT_SECURITY__ALLOWED_ORIGINS")

    # Start with defaults for Docker support
    allowed_hosts = DEFAULT_ALLOWED_HOSTS.copy()
    allowed_origins = DEFAULT_ALLOWED_ORIGINS.copy()

    # Add custom hosts from environment variable
    if allowed_hosts_env:
        try:
            custom_hosts = json.loads(allowed_hosts_env)
        except json.JSONDecodeError:
            # Fallback: treat as comma-separated string
            custom_hosts = [h.strip() for h in allowed_hosts_env.split(",") if h.strip()]
        # Merge with defaults (avoid duplicates)
        allowed_hosts = list(set(allowed_hosts + custom_hosts))

    # Add custom origins from environment variable
    if allowed_origins_env:
        try:
            custom_origins = json.loads(allowed_origins_env)
        except json.JSONDecodeError:
            # Fallback: treat as comma-separated string
            custom_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
        # Merge with defaults (avoid duplicates)
        allowed_origins = list(set(allowed_origins + custom_origins))

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


# Create MCP server with stateless mode enabled
# Stateless mode auto-creates sessions for unknown session IDs, making the server
# resilient to restarts and eliminating "No valid session ID" errors
mcp = FastMCP(
    "Scraper MCP",
    instructions=(
        "A web scraping MCP server that provides efficient webpage scraping tools. "
        "Supports scraping HTML content, converting to markdown, extracting text, "
        "and extracting links from webpages. Also includes resources for accessing "
        "cache, configuration, and server information, plus prompts for common "
        "analysis workflows."
    ),
    stateless_http=True,  # Accept requests without requiring initialize handshake
    transport_security=_get_transport_security_settings(),  # DNS rebinding protection config
)


# Register MCP tools
register_scraping_tools(mcp)

# Register optional cache management tools
if ENABLE_CACHE_TOOLS:
    register_cache_tools(mcp)

# Snapshot availability because tool registration only happens during startup.
PERPLEXITY_TOOLS_AVAILABLE = PerplexityService.is_available()
if PERPLEXITY_TOOLS_AVAILABLE:
    register_perplexity_tools(mcp)


# Register admin API routes
mcp.custom_route("/healthz", methods=["GET"])(health_check)
mcp.custom_route("/api/stats", methods=["GET"])(api_stats)
mcp.custom_route("/api/cache/clear", methods=["POST"])(api_cache_clear)
mcp.custom_route("/api/config", methods=["GET"])(api_config_get)
mcp.custom_route("/api/config", methods=["POST"])(api_config_update)
mcp.custom_route("/api/requests/{request_id}/details", methods=["GET"])(api_request_details)

# Register dashboard route
mcp.custom_route("/", methods=["GET"])(dashboard_view)


def run_server(
    transport: Transport = "streamable-http",
    host: str = "0.0.0.0",
    port: int = 8000,
    enable_resources: bool = False,
    enable_prompts: bool = False,
) -> None:
    """Run the MCP server.

    Args:
        transport: Transport type ('streamable-http' or 'sse')
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8000)
        enable_resources: Enable MCP resources (default: False, disabled to reduce context)
        enable_prompts: Enable MCP prompts (default: False, disabled to reduce context)
    """
    # Register resources if enabled via CLI flag OR environment variable
    if enable_resources or ENABLE_RESOURCES_ENV:
        from scraper_mcp.resources import register_resources

        register_resources(
            mcp,
            perplexity_tools_available=PERPLEXITY_TOOLS_AVAILABLE,
        )

    # Register prompts if enabled via CLI flag OR environment variable
    if enable_prompts or ENABLE_PROMPTS_ENV:
        from scraper_mcp.prompts import register_prompts

        register_prompts(mcp)

    # Configure host and port via settings
    mcp.settings.host = host
    mcp.settings.port = port

    # Run server with specified transport
    mcp.run(transport=transport)


if __name__ == "__main__":
    run_server()
