"""Scraper providers for different scraping backends."""

from scraper_mcp.providers.base import ScraperProvider, ScrapeResult
from scraper_mcp.providers.requests_provider import RequestsProvider

__all__ = ["ScraperProvider", "ScrapeResult", "RequestsProvider"]
