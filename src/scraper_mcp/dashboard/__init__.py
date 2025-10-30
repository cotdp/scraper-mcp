"""Web-based monitoring dashboard for Scraper MCP.

This module provides a web UI for monitoring server status, testing tools,
and configuring runtime settings. The dashboard is accessible at the root
endpoint (/) and provides:
- Real-time server statistics and metrics
- Interactive playground for testing scraping tools
- Configuration management interface

The dashboard serves a single-page HTML application with embedded CSS
and JavaScript from the templates/ directory.
"""

from scraper_mcp.dashboard.router import dashboard

__all__ = [
    "dashboard",
]
