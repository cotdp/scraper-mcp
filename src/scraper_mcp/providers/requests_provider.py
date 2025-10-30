"""Basic scraper provider using Python requests library with disk-based caching."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from urllib.parse import urlencode, urlparse

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
        user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        cache_enabled: bool = True,
    ) -> None:
        """Initialize the requests provider with caching support.

        Args:
            timeout: Request timeout in seconds (default: 30)
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Initial delay between retries in seconds (default: 1.0)
            user_agent: User agent string (default: Chrome 131 on macOS)
            cache_enabled: Enable HTTP caching (default: True)
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.user_agent = user_agent
        self.cache_enabled = cache_enabled

        # Initialize standard requests session
        self.session = requests.Session()

        # ScrapeOps proxy configuration (optional, enabled if API key present)
        self.scrapeops_api_key = os.getenv("SCRAPEOPS_API_KEY")
        self.scrapeops_enabled = bool(self.scrapeops_api_key)

        if self.scrapeops_enabled:
            # ScrapeOps configuration options with sensible defaults
            self.scrapeops_render_js = os.getenv("SCRAPEOPS_RENDER_JS", "false").lower() in ("true", "1", "yes")
            self.scrapeops_residential = os.getenv("SCRAPEOPS_RESIDENTIAL", "false").lower() in ("true", "1", "yes")
            self.scrapeops_country = os.getenv("SCRAPEOPS_COUNTRY", "")
            self.scrapeops_keep_headers = os.getenv("SCRAPEOPS_KEEP_HEADERS", "false").lower() in ("true", "1", "yes")
            self.scrapeops_device = os.getenv("SCRAPEOPS_DEVICE", "desktop")

            logger.info(
                f"RequestsProvider initialized with ScrapeOps proxy enabled "
                f"(render_js={self.scrapeops_render_js}, residential={self.scrapeops_residential})"
            )

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

    def _build_scrapeops_url(self, target_url: str) -> str:
        """Build ScrapeOps proxy URL with configured options.

        Args:
            target_url: The target URL to scrape

        Returns:
            ScrapeOps proxy URL with all configured parameters
        """
        params = {
            "api_key": self.scrapeops_api_key,
            "url": target_url,
        }

        # Add optional parameters if configured
        if self.scrapeops_render_js:
            params["render_js"] = "true"

        if self.scrapeops_residential:
            params["residential"] = "true"

        if self.scrapeops_country:
            params["country"] = self.scrapeops_country

        if self.scrapeops_keep_headers:
            params["keep_headers"] = "true"

        if self.scrapeops_device and self.scrapeops_device != "desktop":
            params["device"] = self.scrapeops_device

        # Build full proxy URL
        proxy_url = f"https://proxy.scrapeops.io/v1/?{urlencode(params)}"
        return proxy_url

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

        # Set default user agent if not provided (unless using ScrapeOps)
        if "User-Agent" not in headers and not self.scrapeops_enabled:
            headers["User-Agent"] = self.user_agent

        # Determine request URL (original or via ScrapeOps proxy)
        original_url = url
        if self.scrapeops_enabled:
            request_url = self._build_scrapeops_url(url)
            logger.debug(f"Using ScrapeOps proxy for URL: {url}")
        else:
            request_url = url

        # Check cache if enabled (use original URL for cache key)
        cache_key = None
        if self.cache_enabled and self.cache_manager:
            # Generate cache key using original URL (not proxy URL)
            cache_key = self.cache_manager.generate_cache_key(
                url=original_url,
                headers=headers,
            )

            # Try to get from cache
            cached_result = self.cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache HIT for URL: {original_url}")
                # Add cache metadata
                cached_result.metadata["from_cache"] = True
                return cached_result

            logger.debug(f"Cache MISS for URL: {original_url}")

        # Retry loop with exponential backoff
        last_exception: Exception | None = None
        attempt = 0

        while attempt <= max_retries:
            try:
                # Run requests in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.session.get(request_url, headers=headers, timeout=timeout),
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

                # Add ScrapeOps metadata if enabled
                if self.scrapeops_enabled:
                    metadata["scrapeops_enabled"] = True
                    metadata["scrapeops_render_js"] = self.scrapeops_render_js

                result = ScrapeResult(
                    url=original_url,  # Use original URL, not proxy URL
                    content=response.text,
                    status_code=response.status_code,
                    content_type=response.headers.get("Content-Type"),
                    metadata=metadata,
                )

                # Store in cache if enabled
                if self.cache_enabled and self.cache_manager and cache_key:
                    ttl = self.cache_manager.get_ttl_for_url(original_url)
                    self.cache_manager.set(cache_key, result, expire=ttl)
                    logger.debug(f"Cached result for URL: {original_url} (TTL: {ttl}s)")

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
                    f"Retry attempt {attempt}/{max_retries} for {original_url} "
                    f"after {delay:.2f}s delay"
                )

                # Sleep before retry (run in thread pool to not block event loop)
                await asyncio.sleep(delay)

        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected error in retry loop")
