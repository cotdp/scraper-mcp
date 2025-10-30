"""MCP scraping tools and business logic.

This module provides the core scraping functionality exposed as MCP tools:
- scrape_url: Raw HTML content retrieval
- scrape_url_markdown: HTML to Markdown conversion
- scrape_url_text: Plain text extraction
- scrape_extract_links: Link discovery and extraction

The tools module follows a router -> service pattern:
- router.py: MCP tool definitions and registration
- service.py: Business logic for scraping, parsing, and batch operations

All tools support:
- Batch operations (multiple URLs)
- Configurable timeouts and retries
- CSS selector filtering
- Concurrent execution with semaphore control
- Error handling with graceful degradation
"""

from scraper_mcp.tools.router import (
    register_cache_tools,
    register_scraping_tools,
    scrape_extract_links,
    scrape_url,
    scrape_url_markdown,
    scrape_url_text,
)
from scraper_mcp.tools.service import (
    batch_extract_links,
    batch_scrape_urls,
    batch_scrape_urls_markdown,
    batch_scrape_urls_text,
    clean_metadata,
)

__all__ = [
    # MCP tool functions
    "scrape_url",
    "scrape_url_markdown",
    "scrape_url_text",
    "scrape_extract_links",
    # Registration functions
    "register_scraping_tools",
    "register_cache_tools",
    # Service functions
    "batch_scrape_urls",
    "batch_scrape_urls_markdown",
    "batch_scrape_urls_text",
    "batch_extract_links",
    "clean_metadata",
]
