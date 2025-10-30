"""MCP server for web scraping functionality."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from scraper_mcp.cache import clear_all_cache, clear_expired_cache, get_cache_stats
from scraper_mcp.providers import RequestsProvider, ScraperProvider
from scraper_mcp.utils import extract_links, extract_metadata, html_to_markdown, html_to_text

# Create MCP server
mcp = FastMCP(
    "Scraper MCP",
    instructions=(
        "A web scraping MCP server that provides efficient webpage scraping tools. "
        "Supports scraping HTML content, converting to markdown, extracting text, "
        "and extracting links from webpages."
    ),
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
DEFAULT_CONCURRENCY = 5


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
) -> ScrapeResultItem:
    """Safely scrape a single URL with error handling.

    Args:
        url: The URL to scrape
        provider: The scraper provider to use
        semaphore: Semaphore for controlling concurrency
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts

    Returns:
        ScrapeResultItem with success/error status
    """
    async with semaphore:
        try:
            result = await provider.scrape(url, timeout=timeout, max_retries=max_retries)
            return ScrapeResultItem(
                url=url,
                success=True,
                data=ScrapeResponse(
                    url=result.url,
                    content=result.content,
                    status_code=result.status_code,
                    content_type=result.content_type,
                    metadata=result.metadata,
                ),
                error=None,
            )
        except Exception as e:
            return ScrapeResultItem(
                url=url,
                success=False,
                data=None,
                error=f"{type(e).__name__}: {str(e)}",
            )


async def batch_scrape_urls(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> BatchScrapeResponse:
    """Scrape multiple URLs concurrently.

    Args:
        urls: List of URLs to scrape
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts per URL
        concurrency: Maximum number of concurrent requests

    Returns:
        BatchScrapeResponse with results for all URLs
    """
    semaphore = asyncio.Semaphore(concurrency)
    provider = _default_provider

    # Create tasks for all URLs
    tasks = [
        scrape_single_url_safe(url, provider, semaphore, timeout, max_retries)
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
) -> ScrapeResultItem:
    """Safely scrape a single URL and convert to markdown with error handling.

    Args:
        url: The URL to scrape
        provider: The scraper provider to use
        semaphore: Semaphore for controlling concurrency
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        strip_tags: List of HTML tags to strip

    Returns:
        ScrapeResultItem with success/error status
    """
    async with semaphore:
        try:
            result = await provider.scrape(url, timeout=timeout, max_retries=max_retries)
            markdown_content = html_to_markdown(result.content, strip_tags=strip_tags)
            page_metadata = extract_metadata(result.content)

            return ScrapeResultItem(
                url=url,
                success=True,
                data=ScrapeResponse(
                    url=result.url,
                    content=markdown_content,
                    status_code=result.status_code,
                    content_type=result.content_type,
                    metadata={**result.metadata, "page_metadata": page_metadata},
                ),
                error=None,
            )
        except Exception as e:
            return ScrapeResultItem(
                url=url,
                success=False,
                data=None,
                error=f"{type(e).__name__}: {str(e)}",
            )


async def batch_scrape_urls_markdown(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> BatchScrapeResponse:
    """Scrape multiple URLs concurrently and convert to markdown.

    Args:
        urls: List of URLs to scrape
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts per URL
        strip_tags: List of HTML tags to strip
        concurrency: Maximum number of concurrent requests

    Returns:
        BatchScrapeResponse with markdown results for all URLs
    """
    semaphore = asyncio.Semaphore(concurrency)
    provider = _default_provider

    tasks = [
        scrape_single_url_markdown_safe(
            url, provider, semaphore, timeout, max_retries, strip_tags
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
) -> ScrapeResultItem:
    """Safely scrape a single URL and extract text with error handling.

    Args:
        url: The URL to scrape
        provider: The scraper provider to use
        semaphore: Semaphore for controlling concurrency
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        strip_tags: List of HTML tags to strip

    Returns:
        ScrapeResultItem with success/error status
    """
    async with semaphore:
        try:
            result = await provider.scrape(url, timeout=timeout, max_retries=max_retries)
            text_content = html_to_text(result.content, strip_tags=strip_tags)
            page_metadata = extract_metadata(result.content)

            return ScrapeResultItem(
                url=url,
                success=True,
                data=ScrapeResponse(
                    url=result.url,
                    content=text_content,
                    status_code=result.status_code,
                    content_type=result.content_type,
                    metadata={**result.metadata, "page_metadata": page_metadata},
                ),
                error=None,
            )
        except Exception as e:
            return ScrapeResultItem(
                url=url,
                success=False,
                data=None,
                error=f"{type(e).__name__}: {str(e)}",
            )


async def batch_scrape_urls_text(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> BatchScrapeResponse:
    """Scrape multiple URLs concurrently and extract text.

    Args:
        urls: List of URLs to scrape
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts per URL
        strip_tags: List of HTML tags to strip
        concurrency: Maximum number of concurrent requests

    Returns:
        BatchScrapeResponse with text results for all URLs
    """
    semaphore = asyncio.Semaphore(concurrency)
    provider = _default_provider

    tasks = [
        scrape_single_url_text_safe(
            url, provider, semaphore, timeout, max_retries, strip_tags
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
) -> LinkResultItem:
    """Safely extract links from a single URL with error handling.

    Args:
        url: The URL to scrape
        provider: The scraper provider to use
        semaphore: Semaphore for controlling concurrency
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts

    Returns:
        LinkResultItem with success/error status
    """
    async with semaphore:
        try:
            result = await provider.scrape(url, timeout=timeout, max_retries=max_retries)
            links = extract_links(result.content, base_url=result.url)

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
            return LinkResultItem(
                url=url,
                success=False,
                data=None,
                error=f"{type(e).__name__}: {str(e)}",
            )


async def batch_extract_links(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> BatchLinksResponse:
    """Extract links from multiple URLs concurrently.

    Args:
        urls: List of URLs to scrape
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts per URL
        concurrency: Maximum number of concurrent requests

    Returns:
        BatchLinksResponse with link extraction results for all URLs
    """
    semaphore = asyncio.Semaphore(concurrency)
    provider = _default_provider

    tasks = [
        extract_links_single_safe(url, provider, semaphore, timeout, max_retries)
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
    urls: str | list[str],
    timeout: int = 30,
    max_retries: int = 3,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> ScrapeResponse | BatchScrapeResponse:
    """Scrape raw HTML content from one or more URLs.

    Args:
        urls: Single URL string or list of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        concurrency: Maximum concurrent requests for batch operations (default: 5)

    Returns:
        ScrapeResponse for single URL or BatchScrapeResponse for multiple URLs
    """
    # Route to appropriate handler
    if isinstance(urls, str):
        # Single URL - use existing logic
        provider = get_provider(urls)
        result = await provider.scrape(urls, timeout=timeout, max_retries=max_retries)

        return ScrapeResponse(
            url=result.url,
            content=result.content,
            status_code=result.status_code,
            content_type=result.content_type,
            metadata=result.metadata,
        )
    else:
        # Multiple URLs - use batch handler
        return await batch_scrape_urls(urls, timeout, max_retries, concurrency)


@mcp.tool()
async def scrape_url_markdown(
    urls: str | list[str],
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> ScrapeResponse | BatchScrapeResponse:
    """Scrape one or more URLs and convert the content to markdown format.

    Args:
        urls: Single URL string or list of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        strip_tags: List of HTML tags to strip (e.g., ['script', 'style'])
        concurrency: Maximum concurrent requests for batch operations (default: 5)

    Returns:
        ScrapeResponse for single URL or BatchScrapeResponse for multiple URLs with markdown content
    """
    # Route to appropriate handler
    if isinstance(urls, str):
        # Single URL - use existing logic
        provider = get_provider(urls)
        result = await provider.scrape(urls, timeout=timeout, max_retries=max_retries)

        # Convert HTML to markdown
        markdown_content = html_to_markdown(result.content, strip_tags=strip_tags)

        # Extract page metadata
        page_metadata = extract_metadata(result.content)

        return ScrapeResponse(
            url=result.url,
            content=markdown_content,
            status_code=result.status_code,
            content_type=result.content_type,
            metadata={**result.metadata, "page_metadata": page_metadata},
        )
    else:
        # Multiple URLs - use batch handler
        return await batch_scrape_urls_markdown(
            urls, timeout, max_retries, strip_tags, concurrency
        )


@mcp.tool()
async def scrape_url_text(
    urls: str | list[str],
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> ScrapeResponse | BatchScrapeResponse:
    """Scrape one or more URLs and extract plain text content.

    Args:
        urls: Single URL string or list of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        strip_tags: List of HTML tags to strip (default: script, style, meta, link, noscript)
        concurrency: Maximum concurrent requests for batch operations (default: 5)

    Returns:
        ScrapeResponse for single URL or BatchScrapeResponse for multiple URLs with plain text content
    """
    # Route to appropriate handler
    if isinstance(urls, str):
        # Single URL - use existing logic
        provider = get_provider(urls)
        result = await provider.scrape(urls, timeout=timeout, max_retries=max_retries)

        # Convert HTML to text
        text_content = html_to_text(result.content, strip_tags=strip_tags)

        # Extract page metadata
        page_metadata = extract_metadata(result.content)

        return ScrapeResponse(
            url=result.url,
            content=text_content,
            status_code=result.status_code,
            content_type=result.content_type,
            metadata={**result.metadata, "page_metadata": page_metadata},
        )
    else:
        # Multiple URLs - use batch handler
        return await batch_scrape_urls_text(
            urls, timeout, max_retries, strip_tags, concurrency
        )


@mcp.tool()
async def scrape_extract_links(
    urls: str | list[str],
    timeout: int = 30,
    max_retries: int = 3,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> LinksResponse | BatchLinksResponse:
    """Scrape one or more URLs and extract all links.

    Args:
        urls: Single URL string or list of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        concurrency: Maximum concurrent requests for batch operations (default: 5)

    Returns:
        LinksResponse for single URL or BatchLinksResponse for multiple URLs with extracted links
    """
    # Route to appropriate handler
    if isinstance(urls, str):
        # Single URL - use existing logic
        provider = get_provider(urls)
        result = await provider.scrape(urls, timeout=timeout, max_retries=max_retries)

        # Extract all links
        links = extract_links(result.content, base_url=result.url)

        return LinksResponse(
            url=result.url,
            links=links,
            count=len(links),
        )
    else:
        # Multiple URLs - use batch handler
        return await batch_extract_links(urls, timeout, max_retries, concurrency)


@mcp.tool()
async def cache_stats() -> dict[str, int | float]:
    """Get HTTP cache statistics.

    Returns:
        Dictionary with cache statistics including size, number of entries, and location
    """
    # Get the session from the default provider
    if hasattr(_default_provider, "session"):
        return get_cache_stats(_default_provider.session)
    else:
        return {
            "error": "Cache not available",
            "cache_enabled": False,
        }


@mcp.tool()
async def cache_clear_expired() -> dict[str, int]:
    """Clear expired entries from HTTP cache.

    Returns:
        Dictionary with the number of expired entries removed
    """
    # Get the session from the default provider
    if hasattr(_default_provider, "session"):
        removed = clear_expired_cache(_default_provider.session)
        return {
            "status": "success",
            "expired_entries_removed": removed,
        }
    else:
        return {
            "status": "error",
            "message": "Cache not available",
        }


@mcp.tool()
async def cache_clear_all() -> dict[str, str]:
    """Clear all entries from HTTP cache.

    WARNING: This will remove all cached responses.

    Returns:
        Dictionary with operation status
    """
    # Get the session from the default provider
    if hasattr(_default_provider, "session"):
        clear_all_cache(_default_provider.session)
        return {
            "status": "success",
            "message": "All cache entries cleared",
        }
    else:
        return {
            "status": "error",
            "message": "Cache not available",
        }


def run_server(transport: str = "streamable-http", host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the MCP server.

    Args:
        transport: Transport type ('streamable-http' or 'sse')
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8000)
    """
    mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    run_server()
