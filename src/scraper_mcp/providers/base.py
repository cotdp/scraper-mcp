"""Base provider interface for web scraping."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ScrapeResult:
    """Result from a web scraping operation."""

    url: str
    content: str
    status_code: int
    content_type: str | None
    metadata: dict[str, Any]


class ScraperProvider(ABC):
    """Abstract base class for scraper providers."""

    @abstractmethod
    async def scrape(self, url: str, **kwargs: Any) -> ScrapeResult:
        """Scrape content from a URL.

        Args:
            url: The URL to scrape
            **kwargs: Additional provider-specific options

        Returns:
            ScrapeResult containing the scraped content and metadata
        """
        pass

    @abstractmethod
    def supports_url(self, url: str) -> bool:
        """Check if this provider supports the given URL.

        Args:
            url: The URL to check

        Returns:
            True if this provider can handle the URL
        """
        pass
