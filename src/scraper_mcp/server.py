"""MCP server for web scraping functionality."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from scraper_mcp.providers import RequestsProvider, ScraperProvider
from scraper_mcp.utils import extract_links, extract_metadata, html_to_markdown, html_to_text

# Create MCP server
mcp = FastMCP(
    "Scraper MCP",
    instructions=(
        "A web scraping MCP server that provides efficient webpage scraping tools. "
        "Supports scraping HTML content, converting to markdown, extracting text, "
        "and extracting links from webpages."
    ),
)


class ScrapeResponse(BaseModel):
    """Response model for scrape operations."""

    url: str = Field(description="The final URL after any redirects")
    content: str = Field(description="The scraped content")
    status_code: int = Field(description="HTTP status code")
    content_type: str | None = Field(description="Content-Type header value")
    metadata: dict[str, Any] = Field(description="Additional metadata from the scrape")


class LinksResponse(BaseModel):
    """Response model for link extraction."""

    url: str = Field(description="The URL that was scraped")
    links: list[dict[str, str]] = Field(description="List of extracted links")
    count: int = Field(description="Total number of links found")


# Initialize default provider
_default_provider: ScraperProvider = RequestsProvider()


def get_provider(url: str) -> ScraperProvider:
    """Get the appropriate provider for a URL.

    Args:
        url: The URL to scrape

    Returns:
        A scraper provider that supports the URL

    Raises:
        ValueError: If no provider supports the URL
    """
    # For now, just use the default provider
    # In the future, we can add more providers and select based on URL
    if _default_provider.supports_url(url):
        return _default_provider

    raise ValueError(f"No provider supports URL: {url}")


@mcp.tool()
async def scrape_url(
    url: str,
    timeout: int = 30,
) -> ScrapeResponse:
    """Scrape raw HTML content from a URL.

    Args:
        url: The URL to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        ScrapeResponse containing the raw HTML content and metadata
    """
    provider = get_provider(url)
    result = await provider.scrape(url, timeout=timeout)

    return ScrapeResponse(
        url=result.url,
        content=result.content,
        status_code=result.status_code,
        content_type=result.content_type,
        metadata=result.metadata,
    )


@mcp.tool()
async def scrape_url_markdown(
    url: str,
    timeout: int = 30,
    strip_tags: list[str] | None = None,
) -> ScrapeResponse:
    """Scrape a URL and convert the content to markdown format.

    Args:
        url: The URL to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        strip_tags: List of HTML tags to strip (e.g., ['script', 'style'])

    Returns:
        ScrapeResponse containing markdown formatted content
    """
    provider = get_provider(url)
    result = await provider.scrape(url, timeout=timeout)

    # Convert HTML to markdown
    markdown_content = html_to_markdown(result.content, strip_tags=strip_tags)

    # Extract page metadata
    page_metadata = extract_metadata(result.content)

    return ScrapeResponse(
        url=result.url,
        content=markdown_content,
        status_code=result.status_code,
        content_type=result.content_type,
        metadata={**result.metadata, "page_metadata": page_metadata},
    )


@mcp.tool()
async def scrape_url_text(
    url: str,
    timeout: int = 30,
    strip_tags: list[str] | None = None,
) -> ScrapeResponse:
    """Scrape a URL and extract plain text content.

    Args:
        url: The URL to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        strip_tags: List of HTML tags to strip (default: script, style, meta, link, noscript)

    Returns:
        ScrapeResponse containing plain text content
    """
    provider = get_provider(url)
    result = await provider.scrape(url, timeout=timeout)

    # Convert HTML to text
    text_content = html_to_text(result.content, strip_tags=strip_tags)

    # Extract page metadata
    page_metadata = extract_metadata(result.content)

    return ScrapeResponse(
        url=result.url,
        content=text_content,
        status_code=result.status_code,
        content_type=result.content_type,
        metadata={**result.metadata, "page_metadata": page_metadata},
    )


@mcp.tool()
async def scrape_extract_links(
    url: str,
    timeout: int = 30,
) -> LinksResponse:
    """Scrape a URL and extract all links.

    Args:
        url: The URL to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        LinksResponse containing all extracted links with their text and titles
    """
    provider = get_provider(url)
    result = await provider.scrape(url, timeout=timeout)

    # Extract all links
    links = extract_links(result.content, base_url=result.url)

    return LinksResponse(
        url=result.url,
        links=links,
        count=len(links),
    )


def run_server(transport: str = "streamable-http", host: str = "0.0.0.0", port: int = 8000) -> None:
    """Run the MCP server.

    Args:
        transport: Transport type ('streamable-http' or 'sse')
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8000)
    """
    mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    run_server()
