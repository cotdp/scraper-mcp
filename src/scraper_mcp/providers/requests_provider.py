"""Basic scraper provider using Python requests library."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import requests

from scraper_mcp.providers.base import ScrapeResult, ScraperProvider


class RequestsProvider(ScraperProvider):
    """Basic web scraper using the requests library."""

    def __init__(
        self,
        timeout: int = 30,
        user_agent: str = "Mozilla/5.0 (compatible; ScraperMCP/0.1.0)",
    ) -> None:
        """Initialize the requests provider.

        Args:
            timeout: Request timeout in seconds
            user_agent: User agent string to use for requests
        """
        self.timeout = timeout
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
        """Scrape content from a URL using requests.

        Args:
            url: The URL to scrape
            **kwargs: Additional options (timeout, headers, etc.)

        Returns:
            ScrapeResult containing the scraped content and metadata

        Raises:
            Exception: If the request fails
        """
        # Extract options
        timeout = kwargs.get("timeout", self.timeout)
        headers = kwargs.get("headers", {})

        # Set default user agent if not provided
        if "User-Agent" not in headers:
            headers["User-Agent"] = self.user_agent

        # Run requests in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.get(url, headers=headers, timeout=timeout),
        )

        # Raise for bad status codes
        response.raise_for_status()

        # Extract metadata
        metadata = {
            "headers": dict(response.headers),
            "encoding": response.encoding,
            "elapsed_ms": response.elapsed.total_seconds() * 1000,
        }

        return ScrapeResult(
            url=response.url,
            content=response.text,
            status_code=response.status_code,
            content_type=response.headers.get("Content-Type"),
            metadata=metadata,
        )
