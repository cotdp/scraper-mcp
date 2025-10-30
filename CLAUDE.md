# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Model Context Protocol (MCP) server for efficient web scraping. Built with Python using FastMCP, providing AI tools with standardized web scraping capabilities through four main tools: raw HTML scraping, markdown conversion, text extraction, and link extraction. All tools support both single URL and batch operations with intelligent retry logic.

## Development Commands

### Environment Setup
```bash
# Install dependencies (uses uv package manager)
uv pip install -e ".[dev]"
```

### Running the Server
```bash
# Run locally with default settings
python -m scraper_mcp

# Run with specific transport and port
python -m scraper_mcp streamable-http 0.0.0.0 8000

# Run with Docker
docker-compose up -d
docker-compose logs -f
docker-compose down
```

### Testing
```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_server.py

# Run specific test class
pytest tests/test_server.py::TestScrapeUrlTool

# Run specific test function
pytest tests/test_server.py::TestScrapeUrlTool::test_scrape_url_success

# Run with verbose output
pytest -v

# Run without coverage report
pytest --no-cov
```

### Code Quality
```bash
# Type checking
mypy src/

# Linting
ruff check .

# Auto-fix linting issues
ruff check . --fix

# Format code
ruff format .
```

## Architecture

### Provider Pattern
The server uses an extensible provider architecture for different scraping backends:

- **`ScraperProvider`** (`providers/base.py`): Abstract interface defining `scrape()` and `supports_url()` methods
- **`RequestsProvider`** (`providers/requests_provider.py`): Default HTTP scraper using `requests` library with exponential backoff retry logic
- **Future extensibility**: Easy to add Playwright, Selenium, or Scrapy providers for JavaScript-heavy sites or specialized scraping

The `get_provider()` function in `server.py` routes URLs to appropriate providers. Currently defaults to `RequestsProvider` for all HTTP/HTTPS URLs.

### Tool Architecture
All four MCP tools (`scrape_url`, `scrape_url_markdown`, `scrape_url_text`, `scrape_extract_links`) follow a dual-mode pattern:

1. **Single URL mode**: Returns `ScrapeResponse` or `LinksResponse` directly
2. **Batch mode**: Accepts `list[str]` URLs, returns `BatchScrapeResponse` or `BatchLinksResponse` with individual results and success/failure counts

Batch operations use `asyncio.Semaphore` (default concurrency: 5) to limit concurrent requests and `asyncio.gather()` for parallel execution.

### HTML Processing Utilities
All utilities in `utils.py` use BeautifulSoup with lxml parser:

- **`html_to_markdown()`**: Converts HTML to markdown using `markdownify` with ATX heading style
- **`html_to_text()`**: Extracts plain text with default stripping of script/style/meta/link/noscript tags
- **`extract_links()`**: Extracts all `<a>` tags with URL resolution using `urllib.parse.urljoin()`
- **`extract_metadata()`**: Extracts `<title>` and all `<meta>` tags (name/property attributes)

### Retry Logic
All scraping operations implement exponential backoff:

- **Default**: 3 retries, 30s timeout, 1s initial delay
- **Backoff schedule**: 1s, 2s, 4s (exponential: `retry_delay * 2^(attempt-1)`)
- **Retryable errors**: `requests.Timeout`, `requests.ConnectionError`, `requests.HTTPError`
- **Metadata tracking**: All responses include `attempts`, `retries`, and `elapsed_ms` fields

### Pydantic Models
Strong typing using Pydantic v2:

- **`ScrapeResult`** (dataclass in `providers/base.py`): Provider return type
- **`ScrapeResponse`** (Pydantic model): Single scrape tool response
- **`LinksResponse`** (Pydantic model): Single link extraction response
- **`ScrapeResultItem`/`LinkResultItem`**: Individual batch operation results with success flag and optional error
- **`BatchScrapeResponse`/`BatchLinksResponse`**: Batch operation responses with totals and results array

## Testing Approach

Tests use pytest-asyncio with pytest-mock for mocking. Key patterns:

- **Fixtures** (`tests/conftest.py`): Provide sample HTML with various features (links, metadata, scripts)
- **Mocking pattern**: Mock `get_provider()` to return a provider with mocked `scrape()` method
- **Batch test pattern**: Test both successful batch operations and partial failures
- **Backward compatibility**: Ensure single URL mode still works after adding batch support

When adding new tools:
1. Create fixtures for test HTML in `conftest.py`
2. Add test class following `Test<ToolName>Tool` naming pattern
3. Test single URL, batch mode, error cases, and parameter variations
4. Mock at the provider level, not the requests level

## Common Development Tasks

### Adding a New Scraping Tool
1. Define Pydantic response model in `server.py`
2. Add utility function to `utils.py` if needed
3. Create `@mcp.tool()` decorated function with dual-mode support (single/batch)
4. Add batch operation helper function following existing patterns
5. Add comprehensive tests in `tests/test_server.py`

### Adding a New Provider
1. Create new file in `providers/` (e.g., `playwright_provider.py`)
2. Subclass `ScraperProvider` and implement `scrape()` and `supports_url()`
3. Update `get_provider()` in `server.py` to route specific URL patterns
4. Add provider-specific tests in `tests/test_providers.py`
5. Update `pyproject.toml` dependencies if needed

### Modifying Retry Behavior
Retry logic is centralized in `RequestsProvider.scrape()` at `providers/requests_provider.py:78-127`. Key parameters:
- `max_retries`: Maximum attempts (default: 3)
- `retry_delay`: Initial backoff delay (default: 1.0s)
- Backoff calculation: `delay = self.retry_delay * (2 ** (attempt - 1))`

To modify retry behavior, adjust the retry loop or add retry parameters to tool signatures.

## Project Configuration

- **Python version**: 3.12+ (uses modern type hints like `str | None`)
- **Package manager**: `uv` for dependency management
- **Build system**: Hatchling
- **Line length**: 100 characters (ruff)
- **Pytest config**: Async mode auto, coverage enabled by default, testpaths: `tests/`
- **Mypy**: Strict mode enabled

## Docker Configuration

- **Base image**: Python 3.12-slim
- **Default port**: 8000
- **Transport**: streamable-http (configurable via env vars)
- **Environment variables**: `TRANSPORT`, `HOST`, `PORT`
- **Restart policy**: unless-stopped (docker-compose)

## MCP Integration

To connect from Claude Desktop, add to MCP settings:
```json
{
  "mcpServers": {
    "scraper": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

The server uses FastMCP which automatically handles transport negotiation and tool registration.
