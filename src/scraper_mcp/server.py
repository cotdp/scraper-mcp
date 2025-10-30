"""MCP server for context-efficient web scraping functionality."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from scraper_mcp.cache import clear_all_cache, clear_expired_cache, get_cache_stats
from scraper_mcp.dashboard.router import dashboard as dashboard_view
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

    content: str = Field(description="The scraped content")
    status_code: int = Field(description="HTTP status code")
    content_type: str | None = Field(description="Content-Type header value")
    metadata: dict[str, Any] = Field(description="Additional metadata from the scrape")


class LinksResponse(BaseModel):
    """Response model for link extraction."""

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

# Initialize proxy settings from environment variables if present
_http_proxy_env = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
_https_proxy_env = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
_no_proxy_env = os.getenv("NO_PROXY") or os.getenv("no_proxy")

if _http_proxy_env or _https_proxy_env:
    _runtime_config["proxy_enabled"] = True
    if _http_proxy_env:
        _runtime_config["http_proxy"] = _http_proxy_env
    if _https_proxy_env:
        _runtime_config["https_proxy"] = _https_proxy_env
    if _no_proxy_env:
        _runtime_config["no_proxy"] = _no_proxy_env

    # Log proxy initialization
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"Proxy enabled from environment variables: "
        f"HTTP_PROXY={_http_proxy_env}, HTTPS_PROXY={_https_proxy_env}, NO_PROXY={_no_proxy_env}"
    )


def get_config(key: str, default: Any = None) -> Any:
    """Get a configuration value with runtime override support.

    Args:
        key: Configuration key
        default: Default value if key not found

    Returns:
        Configuration value
    """
    return _runtime_config.get(key, default)


def clean_metadata(metadata: dict[str, Any], css_selector: str | None = None, elements_matched: int | None = None) -> dict[str, Any]:
    """Clean metadata to only include meaningful optional fields.

    Args:
        metadata: Original metadata dictionary
        css_selector: CSS selector if applied
        elements_matched: Number of elements matched by selector

    Returns:
        Cleaned metadata dictionary with only meaningful fields
    """
    cleaned = {}

    # Always include elapsed_ms if present
    if "elapsed_ms" in metadata:
        cleaned["elapsed_ms"] = metadata["elapsed_ms"]

    # Only include attempts if > 1
    attempts = metadata.get("attempts", 1)
    if attempts > 1:
        cleaned["attempts"] = attempts

    # Only include retries if > 0
    retries = metadata.get("retries", 0)
    if retries > 0:
        cleaned["retries"] = retries

    # Only include from_cache if true
    if metadata.get("from_cache"):
        cleaned["from_cache"] = True

    # Only include proxy_used if true
    if metadata.get("proxy_used"):
        cleaned["proxy_used"] = True
        if "proxy_config" in metadata:
            cleaned["proxy_config"] = metadata["proxy_config"]

    # Only include CSS selector info if selector was applied
    if css_selector:
        cleaned["css_selector_applied"] = css_selector
        if elements_matched is not None:
            cleaned["elements_matched"] = elements_matched

    # Include page_metadata if present (for markdown/text extractions)
    if "page_metadata" in metadata:
        cleaned["page_metadata"] = metadata["page_metadata"]

    # Include headers if present (controlled by include_headers parameter)
    if "headers" in metadata:
        cleaned["headers"] = metadata["headers"]

    return cleaned


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

            # Remove headers if not requested
            if not include_headers:
                result.metadata.pop("headers", None)

            # Clean metadata to remove redundant fields
            metadata = clean_metadata(result.metadata, css_selector, elements_matched)

            # Record successful request metrics
            record_request(
                url=url,
                success=True,
                status_code=result.status_code,
                elapsed_ms=result.metadata.get("elapsed_ms"),
                attempts=result.metadata.get("attempts", 1),
            )

            return ScrapeResultItem(
                url=url,
                success=True,
                data=ScrapeResponse(
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

            # Add page metadata
            metadata = {**result.metadata, "page_metadata": page_metadata}

            # Remove headers if not requested
            if not include_headers:
                metadata.pop("headers", None)

            # Clean metadata to remove redundant fields
            metadata = clean_metadata(metadata, css_selector, elements_matched)

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

            # Add page metadata
            metadata = {**result.metadata, "page_metadata": page_metadata}

            # Remove headers if not requested
            if not include_headers:
                metadata.pop("headers", None)

            # Clean metadata to remove redundant fields
            metadata = clean_metadata(metadata, css_selector, elements_matched)

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
# Test comment
