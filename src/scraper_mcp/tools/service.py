"""Business logic for web scraping tools."""

from __future__ import annotations

import asyncio
from typing import Any

from scraper_mcp.admin.service import DEFAULT_CONCURRENCY
from scraper_mcp.core.providers import default_provider
from scraper_mcp.metrics import record_request
from scraper_mcp.models.links import BatchLinksResponse, LinkResultItem, LinksResponse
from scraper_mcp.models.scrape import (
    BatchScrapeResponse,
    ScrapeResponse,
    ScrapeResultItem,
)
from scraper_mcp.providers import ScraperProvider
from scraper_mcp.utils import (
    extract_links,
    extract_metadata,
    filter_html_by_selector,
    html_to_markdown,
    html_to_text,
)


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
    provider = default_provider

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
    provider = default_provider

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
    provider = default_provider

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
    provider = default_provider

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
