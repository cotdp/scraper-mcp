"""MCP server for web scraping functionality."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from scraper_mcp.cache import clear_all_cache, clear_expired_cache, get_cache_stats
from scraper_mcp.metrics import get_metrics, record_request
from scraper_mcp.providers import RequestsProvider, ScraperProvider
from scraper_mcp.utils import (
    extract_links,
    extract_metadata,
    filter_html_by_selector,
    html_to_markdown,
    html_to_text,
)

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


class ScrapeResponse(BaseModel):
    """Response model for scrape operations."""

    url: str = Field(description="The final URL after any redirects")
    content: str = Field(description="The scraped content")
    status_code: int = Field(description="HTTP status code")
    content_type: str | None = Field(description="Content-Type header value")
    metadata: dict[str, Any] = Field(description="Additional metadata from the scrape")


class LinksResponse(BaseModel):
    """Response model for link extraction."""

    url: str = Field(description="The URL that was scraped")
    links: list[dict[str, str]] = Field(description="List of extracted links")
    count: int = Field(description="Total number of links found")


class ScrapeResultItem(BaseModel):
    """Individual result item for batch operations."""

    url: str = Field(description="The URL that was requested")
    success: bool = Field(description="Whether the scrape was successful")
    data: ScrapeResponse | None = Field(
        default=None, description="Scrape data if successful"
    )
    error: str | None = Field(default=None, description="Error message if failed")


class BatchScrapeResponse(BaseModel):
    """Response model for batch scrape operations."""

    total: int = Field(description="Total number of URLs processed")
    successful: int = Field(description="Number of successful scrapes")
    failed: int = Field(description="Number of failed scrapes")
    results: list[ScrapeResultItem] = Field(description="Results for each URL")


class LinkResultItem(BaseModel):
    """Individual result item for batch link extraction."""

    url: str = Field(description="The URL that was requested")
    success: bool = Field(description="Whether the extraction was successful")
    data: LinksResponse | None = Field(
        default=None, description="Link data if successful"
    )
    error: str | None = Field(default=None, description="Error message if failed")


class BatchLinksResponse(BaseModel):
    """Response model for batch link extraction operations."""

    total: int = Field(description="Total number of URLs processed")
    successful: int = Field(description="Number of successful extractions")
    failed: int = Field(description="Number of failed extractions")
    results: list[LinkResultItem] = Field(description="Results for each URL")


# Initialize default provider
_default_provider: ScraperProvider = RequestsProvider()

# Default concurrency limit for batch operations
DEFAULT_CONCURRENCY = 8

# Runtime configuration overrides (not persisted)
_runtime_config: dict[str, Any] = {
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
    "verify_ssl": False,  # SSL certificate verification (disabled by default)
}


def get_config(key: str, default: Any = None) -> Any:
    """Get a configuration value with runtime override support.

    Args:
        key: Configuration key
        default: Default value if key not found

    Returns:
        Configuration value
    """
    return _runtime_config.get(key, default)


def get_provider(url: str) -> ScraperProvider:
    """Get the appropriate provider for a URL.

    Args:
        url: The URL to scrape

    Returns:
        A scraper provider that supports the URL

    Raises:
        ValueError: If no provider supports the URL
    """
    # For now, just use the default provider
    # In the future, we can add more providers and select based on URL
    if _default_provider.supports_url(url):
        return _default_provider

    raise ValueError(f"No provider supports URL: {url}")


async def scrape_single_url_safe(
    url: str,
    provider: ScraperProvider,
    semaphore: asyncio.Semaphore,
    timeout: int = 30,
    max_retries: int = 3,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> ScrapeResultItem:
    """Safely scrape a single URL with error handling.

    Args:
        url: The URL to scrape
        provider: The scraper provider to use
        semaphore: Semaphore for controlling concurrency
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        css_selector: Optional CSS selector to filter HTML elements
        include_headers: Include HTTP response headers in metadata

    Returns:
        ScrapeResultItem with success/error status
    """
    async with semaphore:
        try:
            result = await provider.scrape(url, timeout=timeout, max_retries=max_retries)

            # Apply CSS selector filter if provided
            content = result.content
            elements_matched = None
            if css_selector:
                content, elements_matched = filter_html_by_selector(content, css_selector)

            # Add filter metadata
            metadata = result.metadata.copy()
            if css_selector:
                metadata["css_selector_applied"] = css_selector
                metadata["elements_matched"] = elements_matched

            # Remove headers if not requested
            if not include_headers:
                metadata.pop("headers", None)

            # Record successful request metrics
            record_request(
                url=url,
                success=True,
                status_code=result.status_code,
                elapsed_ms=metadata.get("elapsed_ms"),
                attempts=metadata.get("attempts", 1),
            )

            return ScrapeResultItem(
                url=url,
                success=True,
                data=ScrapeResponse(
                    url=result.url,
                    content=content,
                    status_code=result.status_code,
                    content_type=result.content_type,
                    metadata=metadata,
                ),
                error=None,
            )
        except Exception as e:
            # Record failed request metrics
            error_msg = f"{type(e).__name__}: {str(e)}"
            record_request(
                url=url,
                success=False,
                error=error_msg,
            )

            return ScrapeResultItem(
                url=url,
                success=False,
                data=None,
                error=error_msg,
            )


async def batch_scrape_urls(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    concurrency: int = DEFAULT_CONCURRENCY,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> BatchScrapeResponse:
    """Scrape multiple URLs concurrently.

    Args:
        urls: List of URLs to scrape
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts per URL
        concurrency: Maximum number of concurrent requests
        css_selector: Optional CSS selector to filter HTML elements
        include_headers: Include HTTP response headers in metadata

    Returns:
        BatchScrapeResponse with results for all URLs
    """
    semaphore = asyncio.Semaphore(concurrency)
    provider = _default_provider

    # Create tasks for all URLs
    tasks = [
        scrape_single_url_safe(url, provider, semaphore, timeout, max_retries, css_selector, include_headers)
        for url in urls
    ]

    # Execute all tasks concurrently
    results = await asyncio.gather(*tasks)

    # Count successes and failures
    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful

    return BatchScrapeResponse(
        total=len(results),
        successful=successful,
        failed=failed,
        results=results,
    )


async def scrape_single_url_markdown_safe(
    url: str,
    provider: ScraperProvider,
    semaphore: asyncio.Semaphore,
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> ScrapeResultItem:
    """Safely scrape a single URL and convert to markdown with error handling.

    Args:
        url: The URL to scrape
        provider: The scraper provider to use
        semaphore: Semaphore for controlling concurrency
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        strip_tags: List of HTML tags to strip
        css_selector: Optional CSS selector to filter HTML elements
        include_headers: Include HTTP response headers in metadata

    Returns:
        ScrapeResultItem with success/error status
    """
    async with semaphore:
        try:
            result = await provider.scrape(url, timeout=timeout, max_retries=max_retries)

            # Apply CSS selector filter if provided (before other processing)
            content = result.content
            elements_matched = None
            if css_selector:
                content, elements_matched = filter_html_by_selector(content, css_selector)

            # Convert to markdown and extract metadata
            markdown_content = html_to_markdown(content, strip_tags=strip_tags)
            page_metadata = extract_metadata(content)

            # Add filter metadata
            metadata = {**result.metadata, "page_metadata": page_metadata}
            if css_selector:
                metadata["css_selector_applied"] = css_selector
                metadata["elements_matched"] = elements_matched

            # Remove headers if not requested
            if not include_headers:
                metadata.pop("headers", None)

            # Record successful request metrics
            record_request(
                url=url,
                success=True,
                status_code=result.status_code,
                elapsed_ms=metadata.get("elapsed_ms"),
                attempts=metadata.get("attempts", 1),
            )

            return ScrapeResultItem(
                url=url,
                success=True,
                data=ScrapeResponse(
                    url=result.url,
                    content=markdown_content,
                    status_code=result.status_code,
                    content_type=result.content_type,
                    metadata=metadata,
                ),
                error=None,
            )
        except Exception as e:
            # Record failed request metrics
            error_msg = f"{type(e).__name__}: {str(e)}"
            record_request(
                url=url,
                success=False,
                error=error_msg,
            )

            return ScrapeResultItem(
                url=url,
                success=False,
                data=None,
                error=error_msg,
            )


async def batch_scrape_urls_markdown(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> BatchScrapeResponse:
    """Scrape multiple URLs concurrently and convert to markdown.

    Args:
        urls: List of URLs to scrape
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts per URL
        strip_tags: List of HTML tags to strip
        concurrency: Maximum number of concurrent requests
        css_selector: Optional CSS selector to filter HTML elements
        include_headers: Include HTTP response headers in metadata

    Returns:
        BatchScrapeResponse with markdown results for all URLs
    """
    semaphore = asyncio.Semaphore(concurrency)
    provider = _default_provider

    tasks = [
        scrape_single_url_markdown_safe(
            url, provider, semaphore, timeout, max_retries, strip_tags, css_selector, include_headers
        )
        for url in urls
    ]

    results = await asyncio.gather(*tasks)

    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful

    return BatchScrapeResponse(
        total=len(results),
        successful=successful,
        failed=failed,
        results=results,
    )


async def scrape_single_url_text_safe(
    url: str,
    provider: ScraperProvider,
    semaphore: asyncio.Semaphore,
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> ScrapeResultItem:
    """Safely scrape a single URL and extract text with error handling.

    Args:
        url: The URL to scrape
        provider: The scraper provider to use
        semaphore: Semaphore for controlling concurrency
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        strip_tags: List of HTML tags to strip
        css_selector: Optional CSS selector to filter HTML elements
        include_headers: Include HTTP response headers in metadata

    Returns:
        ScrapeResultItem with success/error status
    """
    async with semaphore:
        try:
            result = await provider.scrape(url, timeout=timeout, max_retries=max_retries)

            # Apply CSS selector filter if provided (before other processing)
            content = result.content
            elements_matched = None
            if css_selector:
                content, elements_matched = filter_html_by_selector(content, css_selector)

            # Extract text and metadata
            text_content = html_to_text(content, strip_tags=strip_tags)
            page_metadata = extract_metadata(content)

            # Add filter metadata
            metadata = {**result.metadata, "page_metadata": page_metadata}
            if css_selector:
                metadata["css_selector_applied"] = css_selector
                metadata["elements_matched"] = elements_matched

            # Remove headers if not requested
            if not include_headers:
                metadata.pop("headers", None)

            # Record successful request metrics
            record_request(
                url=url,
                success=True,
                status_code=result.status_code,
                elapsed_ms=metadata.get("elapsed_ms"),
                attempts=metadata.get("attempts", 1),
            )

            return ScrapeResultItem(
                url=url,
                success=True,
                data=ScrapeResponse(
                    url=result.url,
                    content=text_content,
                    status_code=result.status_code,
                    content_type=result.content_type,
                    metadata=metadata,
                ),
                error=None,
            )
        except Exception as e:
            # Record failed request metrics
            error_msg = f"{type(e).__name__}: {str(e)}"
            record_request(
                url=url,
                success=False,
                error=error_msg,
            )

            return ScrapeResultItem(
                url=url,
                success=False,
                data=None,
                error=error_msg,
            )


async def batch_scrape_urls_text(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> BatchScrapeResponse:
    """Scrape multiple URLs concurrently and extract text.

    Args:
        urls: List of URLs to scrape
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts per URL
        strip_tags: List of HTML tags to strip
        concurrency: Maximum number of concurrent requests
        css_selector: Optional CSS selector to filter HTML elements
        include_headers: Include HTTP response headers in metadata

    Returns:
        BatchScrapeResponse with text results for all URLs
    """
    semaphore = asyncio.Semaphore(concurrency)
    provider = _default_provider

    tasks = [
        scrape_single_url_text_safe(
            url, provider, semaphore, timeout, max_retries, strip_tags, css_selector, include_headers
        )
        for url in urls
    ]

    results = await asyncio.gather(*tasks)

    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful

    return BatchScrapeResponse(
        total=len(results),
        successful=successful,
        failed=failed,
        results=results,
    )


async def extract_links_single_safe(
    url: str,
    provider: ScraperProvider,
    semaphore: asyncio.Semaphore,
    timeout: int = 30,
    max_retries: int = 3,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> LinkResultItem:
    """Safely extract links from a single URL with error handling.

    Args:
        url: The URL to scrape
        provider: The scraper provider to use
        semaphore: Semaphore for controlling concurrency
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        css_selector: Optional CSS selector to filter HTML before extracting links
        include_headers: Include HTTP response headers in metadata (not used for links)

    Returns:
        LinkResultItem with success/error status
    """
    async with semaphore:
        try:
            result = await provider.scrape(url, timeout=timeout, max_retries=max_retries)

            # Apply CSS selector filter if provided (to scope link extraction)
            content = result.content
            if css_selector:
                content, _ = filter_html_by_selector(content, css_selector)

            # Extract links from (potentially filtered) content
            links = extract_links(content, base_url=result.url)

            # Record successful request metrics
            record_request(
                url=url,
                success=True,
                status_code=result.status_code,
                elapsed_ms=result.metadata.get("elapsed_ms"),
                attempts=result.metadata.get("attempts", 1),
            )

            return LinkResultItem(
                url=url,
                success=True,
                data=LinksResponse(
                    url=result.url,
                    links=links,
                    count=len(links),
                ),
                error=None,
            )
        except Exception as e:
            # Record failed request metrics
            error_msg = f"{type(e).__name__}: {str(e)}"
            record_request(
                url=url,
                success=False,
                error=error_msg,
            )

            return LinkResultItem(
                url=url,
                success=False,
                data=None,
                error=error_msg,
            )


async def batch_extract_links(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    concurrency: int = DEFAULT_CONCURRENCY,
    css_selector: str | None = None,
    include_headers: bool = False,
) -> BatchLinksResponse:
    """Extract links from multiple URLs concurrently.

    Args:
        urls: List of URLs to scrape
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts per URL
        concurrency: Maximum number of concurrent requests
        css_selector: Optional CSS selector to filter HTML before extracting links
        include_headers: Include HTTP response headers in metadata (not used for links)

    Returns:
        BatchLinksResponse with link extraction results for all URLs
    """
    semaphore = asyncio.Semaphore(concurrency)
    provider = _default_provider

    tasks = [
        extract_links_single_safe(url, provider, semaphore, timeout, max_retries, css_selector, include_headers)
        for url in urls
    ]

    results = await asyncio.gather(*tasks)

    successful = sum(1 for r in results if r.success)
    failed = len(results) - successful

    return BatchLinksResponse(
        total=len(results),
        successful=successful,
        failed=failed,
        results=results,
    )


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


# Cache management tools (optional - controlled by ENABLE_CACHE_TOOLS environment variable)
if ENABLE_CACHE_TOOLS:

    @mcp.tool()
    async def cache_stats() -> dict[str, int | float]:
        """Get HTTP cache statistics.

        Returns:
            Dictionary with cache statistics including size, number of entries, and location
        """
        return get_cache_stats()

    @mcp.tool()
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

    @mcp.tool()
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


@mcp.custom_route("/healthz", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for container orchestration.

    Returns:
        JSONResponse with status: healthy
    """
    return JSONResponse({"status": "healthy"})


@mcp.custom_route("/api/stats", methods=["GET"])
async def api_stats(request: Request) -> JSONResponse:
    """Get server statistics and metrics as JSON.

    Returns:
        JSONResponse with server stats including cache and request metrics
    """
    metrics = get_metrics()
    stats = metrics.to_dict()

    # Add cache stats if available
    try:
        stats["cache"] = get_cache_stats()
    except Exception:
        stats["cache"] = {"error": "Cache stats unavailable"}

    return JSONResponse(stats)


@mcp.custom_route("/api/cache/clear", methods=["POST"])
async def api_cache_clear(request: Request) -> JSONResponse:
    """Clear all cache entries.

    Returns:
        JSONResponse with operation status
    """
    try:
        clear_all_cache()
        return JSONResponse({
            "status": "success",
            "message": "Cache cleared successfully"
        })
    except Exception as e:
        return JSONResponse(
            {
                "status": "error",
                "message": str(e)
            },
            status_code=500
        )


@mcp.custom_route("/api/config", methods=["GET"])
async def api_config_get(request: Request) -> JSONResponse:
    """Get current runtime configuration.

    Returns:
        JSONResponse with current config values
    """
    return JSONResponse({
        "config": _runtime_config,
        "defaults": {
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
        },
        "note": "Changes are not persisted and will reset on server restart"
    })


@mcp.custom_route("/api/config", methods=["POST"])
async def api_config_update(request: Request) -> JSONResponse:
    """Update runtime configuration.

    Returns:
        JSONResponse with operation status
    """
    try:
        body = await request.json()
        config_updates = body.get("config", {})

        # Validate and update config
        valid_keys = {
            "concurrency",
            "default_timeout",
            "default_max_retries",
            "cache_ttl_default",
            "cache_ttl_static",
            "cache_ttl_realtime",
            "proxy_enabled",
            "http_proxy",
            "https_proxy",
            "no_proxy",
            "verify_ssl",
        }

        updated = []
        for key, value in config_updates.items():
            if key in valid_keys:
                # Basic type validation
                if key == "concurrency" and isinstance(value, int) and 1 <= value <= 50:
                    _runtime_config[key] = value
                    updated.append(key)
                elif key in ("default_timeout", "default_max_retries") and isinstance(value, int) and value > 0:
                    _runtime_config[key] = value
                    updated.append(key)
                elif key.startswith("cache_ttl_") and isinstance(value, int) and value >= 0:
                    _runtime_config[key] = value
                    updated.append(key)
                elif key in ("proxy_enabled", "verify_ssl") and isinstance(value, bool):
                    _runtime_config[key] = value
                    updated.append(key)
                elif key in ("http_proxy", "https_proxy", "no_proxy") and isinstance(value, str):
                    _runtime_config[key] = value
                    updated.append(key)

        return JSONResponse({
            "status": "success",
            "message": f"Updated {len(updated)} config value(s)",
            "updated": updated,
            "current_config": _runtime_config
        })
    except Exception as e:
        return JSONResponse(
            {
                "status": "error",
                "message": str(e)
            },
            status_code=500
        )


@mcp.custom_route("/", methods=["GET"])
async def dashboard(request: Request) -> HTMLResponse:
    """Serve the monitoring dashboard.

    Returns:
        HTMLResponse with the dashboard UI
    """
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Scraper MCP - Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #fafafa;
            min-height: 100vh;
            padding: 2rem 1.5rem;
            color: #1a1a1a;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        header {
            margin-bottom: 2rem;
        }
        h1 {
            font-size: 1.5rem;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 0.5rem;
            letter-spacing: -0.025em;
        }
        .subtitle {
            color: #737373;
            font-size: 0.875rem;
            font-weight: 400;
        }
        .tabs {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1.5rem;
            border-bottom: 1px solid #e5e5e5;
        }
        .tab {
            padding: 0.75rem 1rem;
            font-size: 0.875rem;
            font-weight: 500;
            color: #737373;
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .tab:hover {
            color: #1a1a1a;
        }
        .tab.active {
            color: #1a1a1a;
            border-bottom-color: #1a1a1a;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 0.75rem;
            margin-bottom: 0.75rem;
        }
        .card {
            background: white;
            border: 1px solid #e5e5e5;
            border-radius: 8px;
            padding: 1rem;
            transition: border-color 0.2s ease;
            margin-bottom: 0.75rem;
        }
        .card:hover {
            border-color: #d4d4d4;
        }
        .card:last-of-type {
            margin-bottom: 0;
        }
        .card h2 {
            font-size: 0.75rem;
            font-weight: 500;
            color: #737373;
            margin-bottom: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
            font-weight: 500;
            color: #1a1a1a;
        }
        .status-badge::before {
            content: '';
            display: inline-block;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #22c55e;
        }
        .status-warning::before {
            background: #f59e0b;
        }
        .stat {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            padding: 0.625rem 0;
            border-bottom: 1px solid #f5f5f5;
        }
        .stat:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }
        .stat:first-child {
            padding-top: 0;
        }
        .stat-label {
            color: #737373;
            font-size: 0.875rem;
            font-weight: 400;
        }
        .stat-value {
            font-weight: 500;
            color: #1a1a1a;
            font-size: 0.875rem;
            font-variant-numeric: tabular-nums;
        }
        .big-stat {
            padding: 1rem 0;
        }
        .big-stat-value {
            font-size: 2rem;
            font-weight: 600;
            color: #1a1a1a;
            line-height: 1;
            letter-spacing: -0.025em;
            font-variant-numeric: tabular-nums;
        }
        .big-stat-label {
            color: #737373;
            margin-top: 0.5rem;
            font-size: 0.875rem;
            font-weight: 400;
        }
        .request-table-container {
            max-height: 320px;
            overflow: auto;
        }
        .request-table-container::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        .request-table-container::-webkit-scrollbar-track {
            background: transparent;
        }
        .request-table-container::-webkit-scrollbar-thumb {
            background: #e5e5e5;
            border-radius: 3px;
        }
        .request-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.75rem;
        }
        .request-table th {
            position: sticky;
            top: 0;
            background: white;
            font-weight: 500;
            color: #737373;
            text-align: left;
            padding: 0.5rem 0.5rem;
            border-bottom: 1px solid #e5e5e5;
            text-transform: uppercase;
            font-size: 0.625rem;
            letter-spacing: 0.05em;
            white-space: nowrap;
        }
        .request-table th:first-child {
            width: 90px;
        }
        .request-table th:nth-child(2) {
            width: 60px;
        }
        .request-table th:nth-child(3) {
            width: 80px;
        }
        .request-table th:nth-child(4) {
            width: auto;
        }
        .request-table td {
            padding: 0.5rem 0.5rem;
            border-bottom: 1px solid #f5f5f5;
            color: #1a1a1a;
        }
        .request-table tbody tr:hover {
            background: #fafafa;
        }
        .request-table .time-col {
            color: #737373;
            white-space: nowrap;
            font-variant-numeric: tabular-nums;
            width: 90px;
        }
        .request-table .status-col {
            white-space: nowrap;
            font-weight: 500;
            width: 60px;
        }
        .request-table .status-success {
            color: #22c55e;
        }
        .request-table .status-error {
            color: #ef4444;
        }
        .request-table .response-time-col {
            text-align: right;
            white-space: nowrap;
            font-variant-numeric: tabular-nums;
            color: #737373;
            width: 80px;
        }
        .request-table .url-col {
            width: auto;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .error-message {
            display: block;
            color: #dc2626;
            font-size: 0.7rem;
            margin-top: 0.25rem;
        }
        .refresh-indicator {
            text-align: center;
            color: #a3a3a3;
            font-size: 0.75rem;
            margin-top: 1.5rem;
            font-variant-numeric: tabular-nums;
        }
        .loading {
            opacity: 0.5;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }
        .pulse {
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }
        .btn {
            display: inline-block;
            padding: 0.5rem 0.5rem;
            font-size: 0.75rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border: 1px solid #e5e5e5;
            border-radius: 6px;
            background: white;
            color: #1a1a1a;
            cursor: pointer;
            transition: all 0.2s ease;
            margin-top: 0.75rem;
            width: 100%;
        }
        .btn:hover {
            border-color: #1a1a1a;
            background: #fafafa;
        }
        .btn:active {
            background: #f5f5f5;
        }
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .form-group {
            margin-bottom: 0.75rem;
        }
        .form-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 0.75rem;
            margin-bottom: 0.75rem;
        }
        .form-group-full {
            grid-column: span 2;
        }
        .form-label {
            display: block;
            font-size: 0.7rem;
            font-weight: 500;
            color: #737373;
            margin-bottom: 0.35rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .form-input {
            width: 100%;
            padding: 0.4rem 0.6rem;
            font-size: 0.875rem;
            border: 1px solid #e5e5e5;
            border-radius: 6px;
            background: white;
            color: #1a1a1a;
            transition: border-color 0.2s ease;
        }
        .form-input:focus {
            outline: none;
            border-color: #1a1a1a;
        }
        .form-input[type="number"] {
            font-variant-numeric: tabular-nums;
        }
        .form-input:disabled {
            background: #f5f5f5;
            color: #a3a3a3;
            cursor: not-allowed;
        }
        .form-help {
            display: block;
            color: #737373;
            font-size: 0.7rem;
            margin-top: 0.25rem;
        }
        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.75rem;
        }
        .checkbox-group input[type="checkbox"] {
            width: 1rem;
            height: 1rem;
            cursor: pointer;
        }
        .checkbox-group label {
            font-size: 0.875rem;
            font-weight: 500;
            color: #1a1a1a;
            cursor: pointer;
            margin: 0;
            text-transform: none;
        }
        .alert {
            padding: 0.75rem 1rem;
            border-radius: 6px;
            margin-bottom: 1rem;
            font-size: 0.875rem;
        }
        .alert-warning {
            background: #fef3c7;
            border: 1px solid #fcd34d;
            color: #92400e;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Scraper MCP</h1>
            <p class="subtitle">Web Scraping Server Dashboard</p>
        </header>

        <div class="tabs">
            <button class="tab active" onclick="switchTab(event, 'dashboard')">Dashboard</button>
            <button class="tab" onclick="switchTab(event, 'playground')">Playground</button>
            <button class="tab" onclick="switchTab(event, 'config')">Config</button>
        </div>

        <div id="dashboard-tab" class="tab-content active">
        <div class="grid">
            <div class="card">
                <h2>Server Status</h2>
                <div class="stat">
                    <span class="stat-label">Status</span>
                    <span class="stat-value"><span id="status" class="status-badge">Healthy</span></span>
                </div>
                <div class="stat">
                    <span class="stat-label">Uptime</span>
                    <span class="stat-value" id="uptime">-</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Started</span>
                    <span class="stat-value" id="start-time">-</span>
                </div>
            </div>

            <div class="card">
                <h2>Request Stats</h2>
                <div class="big-stat">
                    <div class="big-stat-value" id="total-requests">0</div>
                    <div class="big-stat-label">Total Requests</div>
                </div>
                <div class="stat">
                    <span class="stat-label">Success Rate</span>
                    <span class="stat-value" id="success-rate">-</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Failed</span>
                    <span class="stat-value" id="failed-requests">0</span>
                </div>
            </div>

            <div class="card">
                <h2>Retry Stats</h2>
                <div class="stat">
                    <span class="stat-label">Total Retries</span>
                    <span class="stat-value" id="total-retries">0</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Avg Per Request</span>
                    <span class="stat-value" id="avg-retries">-</span>
                </div>
            </div>

            <div class="card">
                <h2>Cache Status</h2>
                <div class="stat">
                    <span class="stat-label">Entries</span>
                    <span class="stat-value" id="cache-entries">-</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Size</span>
                    <span class="stat-value" id="cache-size">-</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Hit Rate</span>
                    <span class="stat-value" id="cache-hit-rate">-</span>
                </div>
                <button class="btn" id="clear-cache-btn" onclick="clearCache()">Clear Cache</button>
            </div>
        </div>

        <div class="card">
            <h2>Recent Requests (Last 10)</h2>
            <div class="request-table-container">
                <table class="request-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Status</th>
                            <th class="response-time-col">Response</th>
                            <th>URL</th>
                        </tr>
                    </thead>
                    <tbody id="recent-requests">
                        <tr><td colspan="4" style="text-align: center; color: #737373; padding: 1rem;">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card">
            <h2>Recent Errors (Last 10)</h2>
            <div class="request-table-container">
                <table class="request-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Status</th>
                            <th class="response-time-col">Attempts</th>
                            <th>URL</th>
                        </tr>
                    </thead>
                    <tbody id="recent-errors">
                        <tr><td colspan="4" style="text-align: center; color: #737373; padding: 1rem;">No errors</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="refresh-indicator" id="refresh-indicator">
            Auto-refresh: <span id="countdown">10</span>s
        </div>
        </div>

        <div id="playground-tab" class="tab-content">
            <div class="card">
                <h2>API Playground</h2>
                <form id="playground-form">
                    <div class="form-group">
                        <label class="form-label" for="test-url">URL</label>
                        <input type="text" id="test-url" class="form-input" placeholder="https://example.com" required>
                        <small class="form-help">Enter a URL to scrape</small>
                    </div>

                    <div class="form-grid">
                        <div class="form-group">
                            <label class="form-label" for="test-tool">Tool</label>
                            <select id="test-tool" class="form-input">
                                <option value="scrape_url">scrape_url (HTML)</option>
                                <option value="scrape_url_markdown" selected>scrape_url_markdown</option>
                                <option value="scrape_url_text">scrape_url_text</option>
                                <option value="scrape_extract_links">scrape_extract_links</option>
                            </select>
                            <small class="form-help">Select scraping tool</small>
                        </div>

                        <div class="form-group">
                            <label class="form-label" for="test-timeout">Timeout (seconds)</label>
                            <input type="number" id="test-timeout" class="form-input" min="1" value="30">
                            <small class="form-help">Request timeout</small>
                        </div>

                        <div class="form-group">
                            <label class="form-label" for="test-retries">Max Retries</label>
                            <input type="number" id="test-retries" class="form-input" min="0" value="3">
                            <small class="form-help">Max retry attempts</small>
                        </div>

                        <div class="form-group">
                            <label class="form-label" for="test-selector">CSS Selector (optional)</label>
                            <input type="text" id="test-selector" class="form-input" placeholder=".article-content">
                            <small class="form-help">Filter HTML elements</small>
                        </div>
                    </div>

                    <button type="submit" class="btn">Run Tool</button>
                </form>
            </div>

            <div class="card" id="playground-response" style="display: none;">
                <h2>Response</h2>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                    <span id="response-status" style="font-size: 0.875rem; color: #737373;"></span>
                    <button onclick="copyResponse(event)" class="btn" style="width: auto; margin: 0; padding: 0.35rem 0.6rem; font-size: 0.7rem;">Copy JSON</button>
                </div>
                <pre id="response-json" style="background: #f5f5f5; padding: 1rem; border-radius: 6px; overflow-x: hidden; font-size: 0.75rem; line-height: 1.5; max-height: 600px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;"><code></code></pre>
            </div>
        </div>

        <div id="config-tab" class="tab-content">
            <div class="alert alert-warning">
                ⚠️ Configuration changes are not persisted and will reset when the server restarts
            </div>

            <div class="card">
                <h2>Runtime Configuration</h2>
                <form id="config-form">
                    <div class="form-grid">
                        <div class="form-group">
                            <label class="form-label" for="concurrency">Concurrency</label>
                            <input type="number" id="concurrency" class="form-input" min="1" max="50" value="8">
                            <small class="form-help">Max concurrent requests (1-50)</small>
                        </div>

                        <div class="form-group">
                            <label class="form-label" for="cache_ttl_default">Cache TTL - Default</label>
                            <input type="number" id="cache_ttl_default" class="form-input" min="0" value="3600">
                            <small class="form-help">Default cache (1h = 3600s)</small>
                        </div>

                        <div class="form-group">
                            <label class="form-label" for="default_timeout">Default Timeout</label>
                            <input type="number" id="default_timeout" class="form-input" min="1" value="30">
                            <small class="form-help">Request timeout in seconds</small>
                        </div>

                        <div class="form-group">
                            <label class="form-label" for="cache_ttl_realtime">Cache TTL - Realtime</label>
                            <input type="number" id="cache_ttl_realtime" class="form-input" min="0" value="300">
                            <small class="form-help">API/live data cache (5m = 300s)</small>
                        </div>

                        <div class="form-group">
                            <label class="form-label" for="default_max_retries">Max Retries</label>
                            <input type="number" id="default_max_retries" class="form-input" min="0" value="3">
                            <small class="form-help">Max retry attempts on failure</small>
                        </div>

                        <div class="form-group">
                            <label class="form-label" for="cache_ttl_static">Cache TTL - Static</label>
                            <input type="number" id="cache_ttl_static" class="form-input" min="0" value="86400">
                            <small class="form-help">Static/CDN cache (24h = 86400s)</small>
                        </div>
                    </div>

                    <h2 style="margin-top: 1.5rem;">Proxy Settings</h2>
                    <div class="checkbox-group">
                        <input type="checkbox" id="proxy_enabled">
                        <label for="proxy_enabled">Enable Proxy</label>
                    </div>

                    <div class="form-grid">
                        <div class="form-group">
                            <label class="form-label" for="http_proxy">HTTP Proxy</label>
                            <input type="text" id="http_proxy" class="form-input" placeholder="http://proxy:8080">
                            <small class="form-help">HTTP proxy URL</small>
                        </div>

                        <div class="form-group">
                            <label class="form-label" for="https_proxy">HTTPS Proxy</label>
                            <input type="text" id="https_proxy" class="form-input" placeholder="https://proxy:8443">
                            <small class="form-help">HTTPS proxy URL</small>
                        </div>

                        <div class="form-group form-group-full">
                            <label class="form-label" for="no_proxy">No Proxy</label>
                            <input type="text" id="no_proxy" class="form-input" placeholder="localhost,127.0.0.1,.local">
                            <small class="form-help">Comma-separated list of hosts to bypass proxy</small>
                        </div>
                    </div>

                    <h2 style="margin-top: 1.5rem;">Security Settings</h2>
                    <div class="checkbox-group">
                        <input type="checkbox" id="verify_ssl">
                        <label for="verify_ssl">Verify SSL Certificates</label>
                    </div>
                    <div class="alert alert-warning" style="margin-top: 0.75rem;">
                        ⚠️ SSL verification is disabled by default. Enable it for production use or when not using self-signed certificates.
                    </div>

                    <button type="submit" class="btn">Apply Changes</button>
                </form>
            </div>
        </div>
    </div>

    <script>
        let countdown = 10;
        let countdownInterval;

        async function fetchStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                updateDashboard(data);
            } catch (error) {
                console.error('Failed to fetch stats:', error);
            }
        }

        function updateDashboard(data) {
            // Server status
            document.getElementById('uptime').textContent = data.uptime.formatted;
            document.getElementById('start-time').textContent = new Date(data.start_time).toLocaleString();

            // Cache stats
            if (data.cache && !data.cache.error) {
                document.getElementById('cache-entries').textContent = data.cache.entry_count.toLocaleString();
                document.getElementById('cache-size').textContent = formatBytes(data.cache.size_bytes);
                const hitRate = data.cache.hits > 0
                    ? ((data.cache.hits / (data.cache.hits + data.cache.misses)) * 100).toFixed(1) + '%'
                    : '0%';
                document.getElementById('cache-hit-rate').textContent = hitRate;
            }

            // Request stats
            document.getElementById('total-requests').textContent = data.requests.total.toLocaleString();
            document.getElementById('success-rate').textContent = data.requests.success_rate.toFixed(1) + '%';
            document.getElementById('failed-requests').textContent = data.requests.failed.toLocaleString();

            // Retry stats
            document.getElementById('total-retries').textContent = data.retries.total.toLocaleString();
            document.getElementById('avg-retries').textContent = data.retries.average_per_request.toFixed(2);

            // Recent requests
            const recentRequestsEl = document.getElementById('recent-requests');
            if (data.recent_requests.length > 0) {
                recentRequestsEl.innerHTML = data.recent_requests.map(req => {
                    const statusClass = req.success ? 'status-success' : 'status-error';
                    const statusText = req.success ? `${req.status_code}` : `${req.status_code || 'ERR'}`;
                    const timestamp = new Date(req.timestamp).toLocaleTimeString();
                    const responseTime = req.elapsed_ms ? `${req.elapsed_ms.toFixed(0)}ms` : '-';
                    return `
                        <tr>
                            <td class="time-col">${timestamp}</td>
                            <td class="status-col ${statusClass}">${statusText}</td>
                            <td class="response-time-col">${responseTime}</td>
                            <td class="url-col" title="${escapeHtml(req.url)}">${escapeHtml(req.url)}</td>
                        </tr>
                    `;
                }).join('');
            } else {
                recentRequestsEl.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #737373; padding: 1rem;">No requests yet</td></tr>';
            }

            // Recent errors
            const recentErrorsEl = document.getElementById('recent-errors');
            if (data.recent_errors.length > 0) {
                recentErrorsEl.innerHTML = data.recent_errors.map(err => {
                    const timestamp = new Date(err.timestamp).toLocaleTimeString();
                    const statusText = err.status_code || 'ERR';
                    const attempts = err.attempts > 1 ? `${err.attempts}x` : '1x';
                    const errorMsg = err.error ? `<span class="error-message">${escapeHtml(err.error)}</span>` : '';
                    return `
                        <tr>
                            <td class="time-col">${timestamp}</td>
                            <td class="status-col status-error">${statusText}</td>
                            <td class="response-time-col">${attempts}</td>
                            <td class="url-col" title="${escapeHtml(err.url)}">${escapeHtml(err.url)}${errorMsg}</td>
                        </tr>
                    `;
                }).join('');
            } else {
                recentErrorsEl.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #737373; padding: 1rem;">No errors</td></tr>';
            }
        }

        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function startCountdown() {
            countdown = 10;
            document.getElementById('countdown').textContent = countdown;

            if (countdownInterval) clearInterval(countdownInterval);

            countdownInterval = setInterval(() => {
                countdown--;
                document.getElementById('countdown').textContent = countdown;

                if (countdown <= 0) {
                    fetchStats();
                    countdown = 10;
                }
            }, 1000);
        }

        async function clearCache() {
            const btn = document.getElementById('clear-cache-btn');

            if (!confirm('Are you sure you want to clear the cache? This will remove all cached responses.')) {
                return;
            }

            btn.disabled = true;
            btn.textContent = 'Clearing...';

            try {
                const response = await fetch('/api/cache/clear', {
                    method: 'POST'
                });

                if (response.ok) {
                    btn.textContent = 'Cleared!';
                    setTimeout(() => {
                        btn.textContent = 'Clear Cache';
                        btn.disabled = false;
                    }, 2000);

                    // Refresh stats immediately
                    fetchStats();
                } else {
                    btn.textContent = 'Failed';
                    setTimeout(() => {
                        btn.textContent = 'Clear Cache';
                        btn.disabled = false;
                    }, 2000);
                }
            } catch (error) {
                console.error('Failed to clear cache:', error);
                btn.textContent = 'Error';
                setTimeout(() => {
                    btn.textContent = 'Clear Cache';
                    btn.disabled = false;
                }, 2000);
            }
        }

        function switchTab(event, tabName) {
            // Update tab buttons
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            event.target.classList.add('active');

            // Update tab content
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(tabName + '-tab').classList.add('active');

            // Load config when switching to config tab
            if (tabName === 'config') {
                loadConfig();
            }
        }

        function toggleProxyInputs() {
            const enabled = document.getElementById('proxy_enabled').checked;
            document.getElementById('http_proxy').disabled = !enabled;
            document.getElementById('https_proxy').disabled = !enabled;
            document.getElementById('no_proxy').disabled = !enabled;
        }

        async function loadConfig() {
            try {
                const response = await fetch('/api/config');
                const data = await response.json();

                // Populate form fields
                Object.entries(data.config).forEach(([key, value]) => {
                    const input = document.getElementById(key);
                    if (input) {
                        if (input.type === 'checkbox') {
                            input.checked = value;
                        } else {
                            input.value = value;
                        }
                    }
                });

                // Update proxy input states
                toggleProxyInputs();
            } catch (error) {
                console.error('Failed to load config:', error);
            }
        }

        async function saveConfig(event) {
            event.preventDefault();

            const form = document.getElementById('config-form');
            const formData = new FormData(form);

            const config = {
                concurrency: parseInt(document.getElementById('concurrency').value),
                default_timeout: parseInt(document.getElementById('default_timeout').value),
                default_max_retries: parseInt(document.getElementById('default_max_retries').value),
                cache_ttl_default: parseInt(document.getElementById('cache_ttl_default').value),
                cache_ttl_static: parseInt(document.getElementById('cache_ttl_static').value),
                cache_ttl_realtime: parseInt(document.getElementById('cache_ttl_realtime').value),
                proxy_enabled: document.getElementById('proxy_enabled').checked,
                http_proxy: document.getElementById('http_proxy').value,
                https_proxy: document.getElementById('https_proxy').value,
                no_proxy: document.getElementById('no_proxy').value,
                verify_ssl: document.getElementById('verify_ssl').checked,
            };

            try {
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ config }),
                });

                const result = await response.json();

                if (result.status === 'success') {
                    alert('Configuration updated successfully!');
                } else {
                    alert('Failed to update configuration: ' + result.message);
                }
            } catch (error) {
                console.error('Failed to save config:', error);
                alert('Error saving configuration');
            }
        }

        async function runPlaygroundTool(event) {
            event.preventDefault();

            const url = document.getElementById('test-url').value;
            const tool = document.getElementById('test-tool').value;
            const timeout = parseInt(document.getElementById('test-timeout').value);
            const maxRetries = parseInt(document.getElementById('test-retries').value);
            const cssSelector = document.getElementById('test-selector').value;

            const responseCard = document.getElementById('playground-response');
            const responseStatus = document.getElementById('response-status');
            const responseJson = document.getElementById('response-json');

            // Show loading state
            responseCard.style.display = 'block';
            responseStatus.textContent = 'Loading...';
            responseJson.querySelector('code').textContent = '';

            try {
                const payload = {
                    jsonrpc: "2.0",
                    id: 1,
                    method: "tools/call",
                    params: {
                        name: tool,
                        arguments: {
                            urls: [url],
                            timeout: timeout,
                            max_retries: maxRetries
                        }
                    }
                };

                // Add optional css_selector
                if (cssSelector) {
                    payload.params.arguments.css_selector = cssSelector;
                }

                const startTime = Date.now();
                const response = await fetch('/mcp', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json, text/event-stream'
                    },
                    body: JSON.stringify(payload)
                });

                const elapsed = Date.now() - startTime;

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const text = await response.text();

                // Parse SSE response - extract JSON from data: line
                const lines = text.trim().split('\\n');
                let result = null;

                for (let i = 0; i < lines.length; i++) {
                    if (lines[i].startsWith('data: ')) {
                        const data = lines[i].substring(6);
                        try {
                            const jsonrpcResponse = JSON.parse(data);
                            // Extract the actual tool result from JSON-RPC response
                            if (jsonrpcResponse.result && jsonrpcResponse.result.structuredContent) {
                                result = jsonrpcResponse.result.structuredContent;
                            } else if (jsonrpcResponse.result) {
                                result = jsonrpcResponse.result;
                            } else if (jsonrpcResponse.error) {
                                throw new Error(jsonrpcResponse.error.message || 'Tool call failed');
                            }
                        } catch (e) {
                            if (e.message && !e.message.includes('Unexpected')) {
                                throw e;
                            }
                            // Skip invalid JSON
                        }
                    }
                }

                if (result) {
                    responseStatus.textContent = `Completed in ${elapsed}ms`;
                    responseJson.querySelector('code').textContent = JSON.stringify(result, null, 2);
                } else {
                    throw new Error('No valid response received');
                }
            } catch (error) {
                responseStatus.textContent = 'Error';
                responseStatus.style.color = '#ef4444';
                responseJson.querySelector('code').textContent = JSON.stringify({
                    error: error.message,
                    details: error.toString()
                }, null, 2);
            }
        }

        function copyResponse(event) {
            const code = document.getElementById('response-json').querySelector('code').textContent;
            navigator.clipboard.writeText(code).then(() => {
                const btn = event.target;
                const originalText = btn.textContent;
                btn.textContent = 'Copied!';
                setTimeout(() => {
                    btn.textContent = originalText;
                }, 2000);
            });
        }

        // Initial load
        fetchStats();
        startCountdown();

        // Setup config form handler
        document.getElementById('config-form').addEventListener('submit', saveConfig);

        // Setup proxy checkbox handler
        document.getElementById('proxy_enabled').addEventListener('change', toggleProxyInputs);

        // Setup playground form handler
        document.getElementById('playground-form').addEventListener('submit', runPlaygroundTool);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


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
# Test comment
