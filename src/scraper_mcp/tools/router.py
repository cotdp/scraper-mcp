"""MCP tool definitions for web scraping and external API integrations."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from scraper_mcp.admin.service import DEFAULT_CONCURRENCY
from scraper_mcp.cache import clear_all_cache, clear_expired_cache, get_cache_stats
from scraper_mcp.models.links import BatchLinksResponse
from scraper_mcp.models.perplexity import PerplexityResponse
from scraper_mcp.models.scrape import BatchScrapeResponse
from scraper_mcp.services.perplexity_service import get_perplexity_service
from scraper_mcp.tools.service import (
    batch_extract_links,
    batch_scrape_urls,
    batch_scrape_urls_markdown,
    batch_scrape_urls_text,
)


async def scrape_url(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    css_selector: str | None = None,
    include_headers: bool = False,
    render_js: bool = False,
) -> BatchScrapeResponse:
    """Scrape one or more URLs and convert the content to markdown format.

    Args:
        urls: List of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        strip_tags: List of HTML tags to strip (e.g., ['script', 'style'])
        css_selector: Optional CSS selector to filter HTML elements before conversion
                     (e.g., ".article-content", "article p")
        include_headers: Include HTTP response headers in metadata (default: False)
        render_js: Enable JavaScript rendering using Playwright for SPAs and dynamic content
                  (default: False). When enabled, uses headless Chromium to render the page.

    Returns:
        BatchScrapeResponse with markdown results for all URLs
    """
    return await batch_scrape_urls_markdown(
        urls,
        timeout,
        max_retries,
        strip_tags,
        DEFAULT_CONCURRENCY,
        css_selector,
        include_headers,
        render_js,
    )


async def scrape_url_html(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    css_selector: str | None = None,
    include_headers: bool = False,
    render_js: bool = False,
) -> BatchScrapeResponse:
    """Scrape raw HTML content from one or more URLs.

    Args:
        urls: List of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        css_selector: Optional CSS selector to filter HTML elements
                     (e.g., "meta", "img, video", ".article-content")
        include_headers: Include HTTP response headers in metadata (default: False)
        render_js: Enable JavaScript rendering using Playwright for SPAs and dynamic content
                  (default: False). When enabled, uses headless Chromium to render the page.

    Returns:
        BatchScrapeResponse with raw HTML results for all URLs
    """
    return await batch_scrape_urls(
        urls, timeout, max_retries, DEFAULT_CONCURRENCY, css_selector, include_headers, render_js
    )


async def scrape_url_text(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    strip_tags: list[str] | None = None,
    css_selector: str | None = None,
    include_headers: bool = False,
    render_js: bool = False,
) -> BatchScrapeResponse:
    """Scrape one or more URLs and extract plain text content.

    Args:
        urls: List of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        strip_tags: List of HTML tags to strip (default: script, style, meta, link, noscript)
        css_selector: Optional CSS selector to filter HTML elements before text extraction
                     (e.g., "#main-content", "article.post")
        include_headers: Include HTTP response headers in metadata (default: False)
        render_js: Enable JavaScript rendering using Playwright for SPAs and dynamic content
                  (default: False). When enabled, uses headless Chromium to render the page.

    Returns:
        BatchScrapeResponse with text results for all URLs
    """
    return await batch_scrape_urls_text(
        urls,
        timeout,
        max_retries,
        strip_tags,
        DEFAULT_CONCURRENCY,
        css_selector,
        include_headers,
        render_js,
    )


async def scrape_extract_links(
    urls: list[str],
    timeout: int = 30,
    max_retries: int = 3,
    css_selector: str | None = None,
    include_headers: bool = False,
    render_js: bool = False,
) -> BatchLinksResponse:
    """Scrape one or more URLs and extract all links.

    Args:
        urls: List of URLs to scrape (must be http:// or https://)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        css_selector: Optional CSS selector to scope link extraction to specific sections
                     (e.g., "nav", "article.main-content")
        include_headers: Include HTTP response headers in metadata (default: False)
        render_js: Enable JavaScript rendering using Playwright for SPAs and dynamic content
                  (default: False). When enabled, uses headless Chromium to render the page.

    Returns:
        BatchLinksResponse with link extraction results for all URLs
    """
    return await batch_extract_links(
        urls,
        timeout,
        max_retries,
        DEFAULT_CONCURRENCY,
        css_selector,
        include_headers,
        render_js,
    )


async def cache_stats() -> dict[str, int | float]:
    """Get HTTP cache statistics.

    Returns:
        Dictionary with cache statistics including size, number of entries, and location
    """
    return get_cache_stats()


async def cache_clear_expired() -> dict[str, int]:
    """Clear expired entries from HTTP cache.

    Returns:
        Dictionary with the number of expired entries removed
    """
    removed = clear_expired_cache()
    return {
        "status": "success",
        "expired_entries_removed": removed,
    }


async def cache_clear_all() -> dict[str, str]:
    """Clear all entries from HTTP cache.

    WARNING: This will remove all cached responses.

    Returns:
        Dictionary with operation status
    """
    clear_all_cache()
    return {
        "status": "success",
        "message": "All cache entries cleared",
    }


def register_scraping_tools(mcp: FastMCP) -> None:
    """Register core scraping tools on the MCP server.

    Tool Registration Pattern:
    -------------------------
    This function uses FastMCP's decorator pattern to register async functions
    as MCP tools. The pattern `mcp.tool()(function)` is equivalent to:

        @mcp.tool()
        async def function(...):
            ...

    By using the functional approach, we can:
    1. Define tools in this module with proper type hints
    2. Keep business logic separate in service.py
    3. Register all tools in one place for clarity
    4. Make tools importable for testing

    The MCP framework automatically:
    - Extracts function signatures for tool schemas
    - Generates OpenAPI-compatible documentation from docstrings
    - Handles JSON serialization of Pydantic models
    - Routes incoming tool calls to the registered functions

    Args:
        mcp: FastMCP server instance to register tools on

    Example:
        >>> from mcp.server.fastmcp import FastMCP
        >>> mcp = FastMCP("Scraper")
        >>> register_scraping_tools(mcp)
        >>> # Tools are now available via MCP protocol
    """
    # Register core scraping tools
    # Each tool is exposed via MCP and documented in the API schema
    mcp.tool()(scrape_url)  # Returns markdown by default
    mcp.tool()(scrape_url_html)  # Returns raw HTML
    mcp.tool()(scrape_url_text)
    mcp.tool()(scrape_extract_links)


def register_cache_tools(mcp: FastMCP) -> None:
    """Register optional cache management tools on the MCP server.

    These tools are only registered when ENABLE_CACHE_TOOLS=true in the
    environment. They provide administrative access to cache operations
    and should be used carefully in production environments.

    Args:
        mcp: FastMCP server instance to register tools on

    Note:
        Cache tools are disabled by default for security. Enable them only
        in development environments or when explicit cache management is needed.
    """
    # Register optional cache management tools
    # These provide direct cache access and statistics
    mcp.tool()(cache_stats)
    mcp.tool()(cache_clear_expired)
    mcp.tool()(cache_clear_all)


# =============================================================================
# Perplexity AI Tools
# =============================================================================


async def perplexity(
    messages: list[dict[str, str]],
    model: str = "sonar",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> PerplexityResponse:
    """Engages in a conversation using Perplexity to search the internet and answer questions.

    Accepts an array of messages (each with a role and content) and returns a chat
    completion response from the Perplexity model.

    Args:
        messages: Array of conversation messages, each with 'role' (system/user/assistant)
                  and 'content' keys. Example: [{"role": "user", "content": "What is AI?"}]
        model: Model to use. Only "sonar" is enabled by default; "sonar-pro",
               "sonar-reasoning", "sonar-reasoning-pro", and "sonar-deep-research"
               must be enabled (opt-in) via the 'perplexity_enabled_models' setting.
               Requesting a disabled model returns an error without making an API call.
        temperature: Response creativity (0-2, default: 0.3). Lower = more focused.
        max_tokens: Maximum response length in tokens (default: 4000)

    Returns:
        PerplexityResponse with content, citations, model used, and usage statistics
    """
    service = get_perplexity_service()
    return await service.chat(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


async def perplexity_reason(
    query: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> PerplexityResponse:
    """Uses the Perplexity reasoning model to perform complex reasoning tasks.

    Accepts a query string and returns a comprehensive reasoned response.
    Uses the sonar-reasoning-pro model optimized for analytical and multi-step reasoning.

    Note: sonar-reasoning-pro is disabled by default and must be enabled (opt-in)
    via the 'perplexity_enabled_models' setting. Until enabled, this tool returns
    an error without making an API call.

    Args:
        query: The query or problem to reason about. Can be a complex question
               requiring analysis, comparison, or multi-step reasoning.
        temperature: Response creativity (0-2, default: 0.3). Lower = more focused.
        max_tokens: Maximum response length in tokens (default: 4000)

    Returns:
        PerplexityResponse with reasoned content, citations, and usage statistics
    """
    service = get_perplexity_service()
    return await service.reason(
        query=query,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def register_perplexity_tools(mcp: FastMCP) -> None:
    """Register Perplexity AI tools on the MCP server.

    These tools are only registered when PERPLEXITY_API_KEY is set in the
    environment. They provide web-grounded AI search and reasoning capabilities.

    Args:
        mcp: FastMCP server instance to register tools on

    Note:
        Perplexity tools require a valid API key from https://perplexity.ai
        Set PERPLEXITY_API_KEY environment variable to enable these tools.
    """
    mcp.tool()(perplexity)
    mcp.tool()(perplexity_reason)
