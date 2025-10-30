"""Provider initialization for the scraper MCP server."""

from scraper_mcp.providers import RequestsProvider, ScraperProvider

# Initialize default provider
# This is used by both the server and tools modules
default_provider: ScraperProvider = RequestsProvider()


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
    if default_provider.supports_url(url):
        return default_provider

    raise ValueError(f"No provider supports URL: {url}")
