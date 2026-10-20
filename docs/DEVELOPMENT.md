# Development Guide

Guide for local development and contributing to Scraper MCP.

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker (optional, for container testing)

## Local Setup

```bash
# Clone the repository
git clone https://github.com/cotdp/scraper-mcp.git
cd scraper-mcp

# Install dependencies
uv pip install -e ".[dev]"

# Run the server
python -m scraper_mcp

# Run with specific transport and port
python -m scraper_mcp streamable-http 0.0.0.0 8000
```

## Development Commands

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=scraper_mcp --cov-report=html

# Type checking
mypy src/

# Linting
ruff check .

# Auto-fix linting issues
ruff check . --fix

# Format code
ruff format .
```

## Project Structure

```
scraper-mcp/
├── src/scraper_mcp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── server.py                  # Main MCP server entry point
│   ├── admin/                     # Admin API (config, stats, cache)
│   │   ├── router.py              # HTTP endpoint handlers
│   │   └── service.py             # Business logic
│   ├── dashboard/                 # Web dashboard
│   │   ├── router.py              # Dashboard routes
│   │   └── templates/
│   │       └── dashboard.html     # Monitoring UI
│   ├── tools/                     # MCP scraping tools
│   │   ├── router.py              # Tool registration
│   │   └── service.py             # Scraping implementations
│   ├── models/                    # Pydantic data models
│   │   ├── scrape.py              # Scrape request/response models
│   │   └── links.py               # Link extraction models
│   ├── providers/                 # Scraping backend providers
│   │   ├── base.py                # Abstract provider interface
│   │   └── requests_provider.py   # HTTP provider (requests library)
│   ├── core/
│   │   └── providers.py           # Provider registry and selection
│   ├── cache.py                   # Request caching (disk-based)
│   ├── cache_manager.py           # Cache lifecycle management
│   ├── metrics.py                 # Request/retry metrics tracking
│   └── utils.py                   # HTML processing utilities
├── tests/                         # Pytest test suite
│   ├── conftest.py                # Test fixtures
│   ├── test_server.py
│   ├── test_tools.py
│   └── test_utils.py
├── docs/                          # Documentation
├── .github/workflows/
│   ├── ci.yml                     # CI/CD: tests, linting
│   └── docker-publish.yml         # Docker image publishing
├── Dockerfile                     # Multi-stage production build
├── docker-compose.yml             # Local development setup
├── pyproject.toml                 # Python dependencies (uv)
└── .env.example                   # Environment configuration template
```

## Architecture

### Provider Pattern

The server uses an extensible provider architecture for scraping backends:

```
ScraperProvider (abstract)
    └── RequestsProvider (default HTTP scraper)
    └── Future: PlaywrightProvider, SeleniumProvider, etc.
```

- **ScraperProvider** (`providers/base.py`): Abstract interface with `scrape()` and `supports_url()` methods
- **RequestsProvider** (`providers/requests_provider.py`): Default implementation using `requests` library with exponential backoff

The `get_provider()` function routes URLs to appropriate providers based on URL patterns.

### Tool Architecture

All MCP tools follow a dual-mode pattern:

1. **Single URL mode**: Returns `ScrapeResponse` directly
2. **Batch mode**: Returns `BatchScrapeResponse` with individual results

Batch operations use `asyncio.Semaphore` for concurrency control.

### HTML Processing

Utilities in `utils.py` use BeautifulSoup with lxml parser:

- `html_to_markdown()`: Converts HTML using `markdownify`
- `html_to_text()`: Extracts plain text
- `extract_links()`: Extracts all `<a>` tags with URL resolution
- `extract_metadata()`: Extracts `<title>` and `<meta>` tags
- `filter_html_by_selector()`: CSS selector filtering

## Building Docker Images

### Build Locally

```bash
docker build -t scraper-mcp:custom .
docker run -p 127.0.0.1:8000:8000 scraper-mcp:custom
```

### With Docker Compose

```bash
docker-compose build
docker-compose up -d
```

### Multi-Platform Build

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t scraper-mcp:multi .
```

## Adding New Features

### Adding a New Tool

1. Define Pydantic response model in `models/`
2. Add utility function to `utils.py` if needed
3. Create tool function in `tools/service.py`
4. Register tool in `tools/router.py`
5. Add tests in `tests/`

### Adding a New Provider

1. Create new file in `providers/` (e.g., `playwright_provider.py`)
2. Subclass `ScraperProvider` and implement `scrape()` and `supports_url()`
3. Update `core/providers.py` to route specific URL patterns
4. Add provider-specific tests
5. Update `pyproject.toml` dependencies if needed

## Testing

### Test Structure

- **Unit tests** (`test_utils.py`): HTML processing, conversion, extraction
- **Provider tests** (`test_providers.py`): HTTP scraping, error handling
- **Integration tests** (`test_server.py`): MCP tool functionality

### Running Specific Tests

```bash
# Specific file
pytest tests/test_utils.py

# Specific class
pytest tests/test_providers.py::TestRequestsProvider

# Specific test
pytest tests/test_server.py::TestScrapeUrlTool::test_scrape_url_success

# Verbose output
pytest -v
```

### Test Fixtures

Fixtures in `tests/conftest.py` provide sample HTML for testing:
- `sample_html`: Complex HTML with various elements
- `simple_html`: Minimal HTML for basic tests
- `html_with_links`: HTML with different link types
- `html_with_metadata`: HTML with meta tags and OpenGraph data

## Code Style

- **Line length**: 100 characters
- **Type hints**: Required for all functions
- **Docstrings**: Google style
- **Imports**: Sorted with `ruff`

## CI/CD

GitHub Actions workflows:

- **ci.yml**: Runs on every PR
  - Python 3.12 tests
  - Type checking (mypy)
  - Linting (ruff)
  - Coverage reporting

- **docker-publish.yml**: Runs on releases
  - Multi-platform builds (amd64, arm64)
  - Pushes to Docker Hub and GHCR
  - Semantic version tags
