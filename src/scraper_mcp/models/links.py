"""Pydantic models for link extraction operations."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LinksResponse(BaseModel):
    """Response model for link extraction."""

    links: list[dict[str, str]] = Field(description="List of extracted links")
    count: int = Field(description="Total number of links found")


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
