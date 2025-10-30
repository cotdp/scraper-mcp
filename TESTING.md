# Testing Guide

This document provides guidance on testing the Scraper MCP server.

## Test Suite

The project includes a comprehensive test suite with **84% code coverage** and **45 passing tests**.

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=scraper_mcp --cov-report=html

# Run specific test file
pytest tests/test_utils.py

# Run specific test class
pytest tests/test_providers.py::TestRequestsProvider

# Run specific test
pytest tests/test_server.py::TestScrapeUrlTool::test_scrape_url_success
```

### Test Coverage

```
Name                                             Stmts   Miss  Cover
----------------------------------------------------------------------
src/scraper_mcp/__init__.py                          1      0   100%
src/scraper_mcp/providers/__init__.py                3      0   100%
src/scraper_mcp/providers/base.py                   18      2    89%
src/scraper_mcp/providers/requests_provider.py      26      2    92%
src/scraper_mcp/server.py                           51      5    90%
src/scraper_mcp/utils.py                            43      0   100%
----------------------------------------------------------------------
TOTAL                                              159     26    84%
```

## Test Structure

### Unit Tests

**tests/test_utils.py** (21 tests)
- HTML to markdown conversion
- HTML to plain text extraction
- Link extraction with URL resolution
- Metadata extraction (title, meta tags, OpenGraph)

**tests/test_providers.py** (12 tests)
- URL validation and support
- HTTP scraping with metadata
- Custom timeout and headers
- Error handling (HTTP errors, timeouts, connection failures)
- Redirect following
- User agent handling

### Integration Tests

**tests/test_server.py** (12 tests)
- `scrape_url` tool functionality
- `scrape_url_markdown` with tag stripping
- `scrape_url_text` with custom stripping
- `scrape_extract_links` with URL resolution

## Manual Integration Testing

To manually test the server with real URLs:

### 1. Start the Server

```bash
# Using Python directly
python -m scraper_mcp

# Using Docker
docker-compose up -d
```

### 2. Test with MCP Inspector

```bash
# Install MCP CLI tools
uv add mcp[cli]

# Run inspector
uv run mcp dev src/scraper_mcp/server.py
```

This will open a web interface where you can:
- List available tools
- Call tools with different parameters
- View responses and metadata
- Test error handling

### 3. Test Individual Tools

You can use the Python client to test tools programmatically:

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_scraper():
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "scraper_mcp"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Test scrape_url
            result = await session.call_tool(
                "scrape_url",
                arguments={"url": "https://example.com"}
            )
            print(f"Scraped {len(result.content)} characters")

asyncio.run(test_scraper())
```

## Continuous Integration

The test suite is designed to run in CI/CD environments:

```yaml
# Example GitHub Actions workflow
- name: Install dependencies
  run: uv pip install -e ".[dev]"

- name: Run tests
  run: pytest --cov=scraper_mcp --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
```

## Test Data

Test fixtures are defined in `tests/conftest.py`:
- `sample_html`: Complex HTML with various elements
- `simple_html`: Minimal HTML for basic tests
- `html_with_links`: HTML with different link types
- `html_with_metadata`: HTML with meta tags and OpenGraph data

## Troubleshooting

### Tests Fail with Import Errors

Make sure you've installed the package in development mode:
```bash
uv pip install -e ".[dev]"
```

### Async Tests Not Running

Ensure pytest-asyncio is installed and configured:
```bash
uv pip install pytest-asyncio
```

### Coverage Reports Missing

Install pytest-cov:
```bash
uv pip install pytest-cov
```

## Adding New Tests

When adding new functionality:

1. **Add unit tests** for individual functions
2. **Add integration tests** for MCP tool functionality
3. **Update fixtures** if new test data is needed
4. **Run tests** to ensure nothing breaks
5. **Check coverage** to ensure new code is tested

Example test structure:

```python
import pytest
from scraper_mcp.utils import new_function

class TestNewFunction:
    """Tests for new_function."""

    def test_basic_case(self):
        """Test basic functionality."""
        result = new_function("input")
        assert result == "expected"

    def test_edge_case(self):
        """Test edge cases."""
        result = new_function("")
        assert result == ""

    def test_error_handling(self):
        """Test error handling."""
        with pytest.raises(ValueError):
            new_function(None)
```
