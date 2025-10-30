"""Basic scraper provider using Python requests library."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlparse

import requests

from scraper_mcp.providers.base import ScrapeResult, ScraperProvider


class RequestsProvider(ScraperProvider):
    """Basic web scraper using the requests library with retry support."""

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        user_agent: str = "Mozilla/5.0 (compatible; ScraperMCP/0.1.0)",
    ) -> None:
        """Initialize the requests provider.

        Args:
            timeout: Request timeout in seconds (default: 30)
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Initial delay between retries in seconds (default: 1.0)
            user_agent: User agent string to use for requests
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.user_agent = user_agent

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
        """Scrape content from a URL using requests with retry logic.

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

        # Retry loop with exponential backoff
        last_exception: Exception | None = None
        attempt = 0

        while attempt <= max_retries:
            try:
                # Run requests in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: requests.get(url, headers=headers, timeout=timeout),
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
                }

                return ScrapeResult(
                    url=response.url,
                    content=response.text,
                    status_code=response.status_code,
                    content_type=response.headers.get("Content-Type"),
                    metadata=metadata,
                )

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

                # Sleep before retry (run in thread pool to not block event loop)
                await asyncio.sleep(delay)

        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected error in retry loop")
