"""MCP tool definitions for web scraping."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from scraper_mcp.admin.service import DEFAULT_CONCURRENCY
from scraper_mcp.cache import clear_all_cache, clear_expired_cache, get_cache_stats
from scraper_mcp.models.links import BatchLinksResponse
from scraper_mcp.models.scrape import BatchScrapeResponse
from scraper_mcp.tools.service import (
    batch_extract_links,
    batch_scrape_urls,
    batch_scrape_urls_markdown,
    batch_scrape_urls_text,
)


async def scrape_url(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> BatchScrapeResponse:
    """Scrape raw HTML content from one or more URLs.

    Args:
        urls: List of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        css_selector: Optional CSS selector to filter HTML elements
                     (e.g., "meta", "img, video", ".article-content")
        include_headers: Include HTTP response headers in metadata (default: False)

    Returns:
        BatchScrapeResponse with results for all URLs
    """
    return await batch_scrape_urls(urls, timeout, max_retries, DEFAULT_CONCURRENCY, css_selector, include_headers)


async def scrape_url_markdown(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> BatchScrapeResponse:
    """Scrape one or more URLs and convert the content to markdown format.

    Args:
        urls: List of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        strip_tags: List of HTML tags to strip (e.g., ['script', 'style'])
        css_selector: Optional CSS selector to filter HTML elements before conversion
                     (e.g., ".article-content", "article p")
        include_headers: Include HTTP response headers in metadata (default: False)

    Returns:
        BatchScrapeResponse with markdown results for all URLs
    """
    return await batch_scrape_urls_markdown(
        urls, timeout, max_retries, strip_tags, DEFAULT_CONCURRENCY, css_selector, include_headers
    )


async def scrape_url_text(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> BatchScrapeResponse:
    """Scrape one or more URLs and extract plain text content.

    Args:
        urls: List of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        strip_tags: List of HTML tags to strip (default: script, style, meta, link, noscript)
        css_selector: Optional CSS selector to filter HTML elements before text extraction
                     (e.g., "#main-content", "article.post")
        include_headers: Include HTTP response headers in metadata (default: False)

    Returns:
        BatchScrapeResponse with text results for all URLs
    """
    return await batch_scrape_urls_text(
        urls, timeout, max_retries, strip_tags, DEFAULT_CONCURRENCY, css_selector, include_headers
    )


async def scrape_extract_links(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> BatchLinksResponse:
    """Scrape one or more URLs and extract all links.

    Args:
        urls: List of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        css_selector: Optional CSS selector to scope link extraction to specific sections
                     (e.g., "nav", "article.main-content")
        include_headers: Include HTTP response headers in metadata (default: False, not used for links)

    Returns:
        BatchLinksResponse with link extraction results for all URLs
    """
    return await batch_extract_links(urls, timeout, max_retries, DEFAULT_CONCURRENCY, css_selector, include_headers)


async def cache_stats() -> dict[str, int | float]:
    """Get HTTP cache statistics.

    Returns:
        Dictionary with cache statistics including size, number of entries, and location
    """
    return get_cache_stats()


async def cache_clear_expired() -> dict[str, int]:
    """Clear expired entries from HTTP cache.

    Returns:
        Dictionary with the number of expired entries removed
    """
    removed = clear_expired_cache()
    return {
        "status": "success",
        "expired_entries_removed": removed,
    }


async def cache_clear_all() -> dict[str, str]:
    """Clear all entries from HTTP cache.

    WARNING: This will remove all cached responses.

    Returns:
        Dictionary with operation status
    """
    clear_all_cache()
    return {
        "status": "success",
        "message": "All cache entries cleared",
    }


def register_scraping_tools(mcp: FastMCP) -> None:
    """Register core scraping tools on the MCP server.

    Args:
        mcp: FastMCP server instance to register tools on
    """
    # Register tool functions with MCP decorator
    mcp.tool()(scrape_url)
    mcp.tool()(scrape_url_markdown)
    mcp.tool()(scrape_url_text)
    mcp.tool()(scrape_extract_links)


def register_cache_tools(mcp: FastMCP) -> None:
    """Register optional cache management tools on the MCP server.

    Args:
        mcp: FastMCP server instance to register tools on
    """
    # Register cache tool functions with MCP decorator
    mcp.tool()(cache_stats)
    mcp.tool()(cache_clear_expired)
    mcp.tool()(cache_clear_all)
