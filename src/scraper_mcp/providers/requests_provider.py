"""Basic scraper provider using Python requests library with disk-based caching."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

import requests

from scraper_mcp.cache_manager import get_cache_manager
from scraper_mcp.providers.base import ScrapeResult, ScraperProvider

# Configure logging
logger = logging.getLogger(__name__)


class RequestsProvider(ScraperProvider):
    """Web scraper using requests library with persistent disk-based caching and retry support."""

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        user_agent: str = "Mozilla/5.0 (compatible; ScraperMCP/0.1.0)",
        cache_enabled: bool = True,
    ) -> None:
        """Initialize the requests provider with caching support.

        Args:
            timeout: Request timeout in seconds (default: 30)
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Initial delay between retries in seconds (default: 1.0)
            user_agent: User agent string to use for requests
            cache_enabled: Enable HTTP caching (default: True)
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.user_agent = user_agent
        self.cache_enabled = cache_enabled

        # Initialize standard requests session
        self.session = requests.Session()

        # Get cache manager if caching is enabled
        if cache_enabled:
            self.cache_manager = get_cache_manager()
            logger.info("RequestsProvider initialized with caching enabled")
        else:
            self.cache_manager = None
            logger.info("RequestsProvider initialized with caching disabled")

    def supports_url(self, url: str) -> bool:
        """Check if this provider supports the given URL.

        Args:
            url: The URL to check

        Returns:
            True if the URL uses http or https scheme
        """
        try:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https")
        except Exception:
            return False

    async def scrape(self, url: str, **kwargs: Any) -> ScrapeResult:
        """Scrape content from a URL using requests with caching and retry logic.

        Args:
            url: The URL to scrape
            **kwargs: Additional options
                - timeout: Request timeout in seconds
                - max_retries: Maximum number of retry attempts
                - headers: Custom HTTP headers

        Returns:
            ScrapeResult containing the scraped content and metadata

        Raises:
            requests.RequestException: If the request fails after all retries
        """
        # Extract options
        timeout = kwargs.get("timeout", self.timeout)
        max_retries = kwargs.get("max_retries", self.max_retries)
        headers = kwargs.get("headers", {})

        # Set default user agent if not provided
        if "User-Agent" not in headers:
            headers["User-Agent"] = self.user_agent

        # Check cache if enabled
        cache_key = None
        if self.cache_enabled and self.cache_manager:
            # Generate cache key
            cache_key = self.cache_manager.generate_cache_key(
                url=url,
                headers=headers,
            )

            # Try to get from cache
            cached_result = self.cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache HIT for URL: {url}")
                # Add cache metadata
                cached_result.metadata["from_cache"] = True
                return cached_result

            logger.debug(f"Cache MISS for URL: {url}")

        # Retry loop with exponential backoff
        last_exception: Exception | None = None
        attempt = 0

        while attempt <= max_retries:
            try:
                # Run requests in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.session.get(url, headers=headers, timeout=timeout),
                )

                # Raise for bad status codes
                response.raise_for_status()

                # Extract metadata including retry info
                metadata = {
                    "headers": dict(response.headers),
                    "encoding": response.encoding,
                    "elapsed_ms": response.elapsed.total_seconds() * 1000,
                    "attempts": attempt + 1,
                    "retries": attempt,
                    "from_cache": False,
                }

                result = ScrapeResult(
                    url=response.url,
                    content=response.text,
                    status_code=response.status_code,
                    content_type=response.headers.get("Content-Type"),
                    metadata=metadata,
                )

                # Store in cache if enabled
                if self.cache_enabled and self.cache_manager and cache_key:
                    ttl = self.cache_manager.get_ttl_for_url(url)
                    self.cache_manager.set(cache_key, result, expire=ttl)
                    logger.debug(f"Cached result for URL: {url} (TTL: {ttl}s)")

                return result

            except (
                requests.Timeout,
                requests.ConnectionError,
                requests.HTTPError,
            ) as e:
                last_exception = e
                attempt += 1

                # If we've exhausted all retries, raise the exception
                if attempt > max_retries:
                    raise

                # Calculate exponential backoff delay
                delay = self.retry_delay * (2 ** (attempt - 1))

                logger.debug(
                    f"Retry attempt {attempt}/{max_retries} for {url} "
                    f"after {delay:.2f}s delay"
                )

                # Sleep before retry (run in thread pool to not block event loop)
                await asyncio.sleep(delay)

        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected error in retry loop")
