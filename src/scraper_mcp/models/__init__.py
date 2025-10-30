"""Pydantic data models for scraping operations and responses.

This module defines the data structures used throughout the scraper,
providing type-safe request/response models for:
- Individual scrape operations (ScrapeResponse)
- Batch scrape operations (BatchScrapeResponse, ScrapeResultItem)
- Link extraction (LinksResponse, BatchLinksResponse, LinkResultItem)

All models use Pydantic v2 for validation and serialization, ensuring
data integrity across the MCP tool interface.
"""

from scraper_mcp.models.links import (
    BatchLinksResponse,
    LinkResultItem,
    LinksResponse,
)
from scraper_mcp.models.scrape import (
    BatchScrapeResponse,
    ScrapeResponse,
    ScrapeResultItem,
)

__all__ = [
    # Scrape models
    "ScrapeResponse",
    "ScrapeResultItem",
    "BatchScrapeResponse",
    # Link extraction models
    "LinksResponse",
    "LinkResultItem",
    "BatchLinksResponse",
]
