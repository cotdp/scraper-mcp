"""Pydantic models for web scraping operations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScrapeResponse(BaseModel):
    """Response model for scrape operations."""

    content: str = Field(description="The scraped content")
    status_code: int = Field(description="HTTP status code")
    content_type: str | None = Field(description="Content-Type header value")
    metadata: dict[str, Any] = Field(description="Additional metadata from the scrape")


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
