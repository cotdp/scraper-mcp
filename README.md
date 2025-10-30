# Scraper MCP

A Model Context Protocol (MCP) server for efficient web scraping. This server provides AI tools with the ability to scrape webpages without having to handle the complexity themselves.

## Features

- **Multiple scraping tools**: Raw HTML, markdown conversion, plain text extraction, and link extraction
- **Provider architecture**: Extensible design supporting multiple scraping backends
- **Docker support**: Easy deployment with Docker and Docker Compose
- **HTTP/SSE transports**: Supports both Streamable HTTP and SSE MCP transports
- **Structured output**: Returns well-typed, validated data that clients can easily process

## Quick Start with Docker

The easiest way to run the server is using Docker Compose:

```bash
# Build and start the server
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the server
docker-compose down
```

The server will be available at `http://localhost:8000/mcp`

## Available Tools

### 1. `scrape_url`
Scrape raw HTML content from a URL.

**Parameters:**
- `url` (string, required): The URL to scrape (http:// or https://)
- `timeout` (integer, optional): Request timeout in seconds (default: 30)
- `max_retries` (integer, optional): Maximum retry attempts on failure (default: 3)

**Returns:**
- `url`: Final URL after redirects
- `content`: Raw HTML content
- `status_code`: HTTP status code
- `content_type`: Content-Type header value
- `metadata`: Additional metadata including:
  - `headers`: Response headers
  - `encoding`: Content encoding
  - `elapsed_ms`: Request duration in milliseconds
  - `attempts`: Total number of attempts made
  - `retries`: Number of retries performed

### 2. `scrape_url_markdown`
Scrape a URL and convert the content to markdown format.

**Parameters:**
- `url` (string, required): The URL to scrape
- `timeout` (integer, optional): Request timeout in seconds (default: 30)
- `max_retries` (integer, optional): Maximum retry attempts on failure (default: 3)
- `strip_tags` (array, optional): List of HTML tags to strip (e.g., ['script', 'style'])

**Returns:**
- Same as `scrape_url` but with markdown-formatted content
- `metadata.page_metadata`: Extracted page metadata (title, description, etc.)
- `metadata.attempts`: Total number of attempts made
- `metadata.retries`: Number of retries performed

### 3. `scrape_url_text`
Scrape a URL and extract plain text content.

**Parameters:**
- `url` (string, required): The URL to scrape
- `timeout` (integer, optional): Request timeout in seconds (default: 30)
- `max_retries` (integer, optional): Maximum retry attempts on failure (default: 3)
- `strip_tags` (array, optional): HTML tags to strip (default: script, style, meta, link, noscript)

**Returns:**
- Same as `scrape_url` but with plain text content
- `metadata.page_metadata`: Extracted page metadata
- `metadata.attempts`: Total number of attempts made
- `metadata.retries`: Number of retries performed

### 4. `scrape_extract_links`
Scrape a URL and extract all links.

**Parameters:**
- `url` (string, required): The URL to scrape
- `timeout` (integer, optional): Request timeout in seconds (default: 30)
- `max_retries` (integer, optional): Maximum retry attempts on failure (default: 3)

**Returns:**
- `url`: The URL that was scraped
- `links`: Array of link objects with `url`, `text`, and `title`
- `count`: Total number of links found

## Local Development

### Prerequisites

- Python 3.12+
- uv package manager

### Setup

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Run the server locally
python -m scraper_mcp

# Run with specific transport and port
python -m scraper_mcp streamable-http 0.0.0.0 8000
```

### Development Commands

```bash
# Run tests
pytest

# Type checking
mypy src/

# Linting and formatting
ruff check .
ruff format .
```

## Docker Deployment

### Build Docker Image

```bash
docker build -t scraper-mcp:latest .
```

### Run with Docker

```bash
# Run with default settings (streamable-http on port 8000)
docker run -p 8000:8000 scraper-mcp:latest

# Run with custom settings
docker run -p 8080:8080 scraper-mcp:latest streamable-http 0.0.0.0 8080
```

### Docker Compose

The `docker-compose.yml` file provides a production-ready configuration:

```yaml
services:
  scraper-mcp:
    build: .
    ports:
      - "8000:8000"
    environment:
      - TRANSPORT=streamable-http
      - HOST=0.0.0.0
      - PORT=8000
    restart: unless-stopped
```

## Connecting from Claude Desktop

To use this server with Claude Desktop, add it to your MCP settings:

```json
{
  "mcpServers": {
    "scraper": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

## Project Structure

```
scraper-mcp/
├── src/
│   └── scraper_mcp/
│       ├── __init__.py
│       ├── __main__.py
│       ├── server.py              # Main MCP server
│       ├── utils.py               # HTML processing utilities
│       └── providers/
│           ├── __init__.py
│           ├── base.py            # Provider interface
│           └── requests_provider.py  # Basic HTTP provider
├── tests/
│   └── __init__.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Architecture

The server uses a provider architecture to support multiple scraping backends:

- **ScraperProvider**: Abstract interface for scraping implementations
- **RequestsProvider**: Basic HTTP scraper using the `requests` library
- **Future providers**: Can add support for Playwright, Selenium, Scrapy, etc.

The provider selection is automatic based on URL patterns, making it easy to add specialized providers for different types of websites.

## Retry Behavior & Error Handling

The scraper includes intelligent retry logic with exponential backoff to handle transient failures:

### Retry Configuration

- **Default max_retries**: 3 attempts
- **Default timeout**: 30 seconds
- **Retry delay**: Exponential backoff starting at 1 second

### Retry Schedule

For the default configuration (max_retries=3):
1. **First attempt**: Immediate
2. **Retry 1**: Wait 1 second
3. **Retry 2**: Wait 2 seconds
4. **Retry 3**: Wait 4 seconds

Total maximum wait time: ~7 seconds before final failure

### What Triggers Retries

The scraper automatically retries on:
- **Network timeouts** (`requests.Timeout`)
- **Connection failures** (`requests.ConnectionError`)
- **HTTP errors** (4xx, 5xx status codes)

### Retry Metadata

All successful responses include retry information in metadata:
```json
{
  "attempts": 2,      // Total attempts made (1 = no retries)
  "retries": 1,       // Number of retries performed
  "elapsed_ms": 234.5 // Total request time in milliseconds
}
```

### Customizing Retry Behavior

```python
# Disable retries
result = await scrape_url("https://example.com", max_retries=0)

# More aggressive retries for flaky sites
result = await scrape_url("https://example.com", max_retries=5, timeout=60)

# Quick fail for time-sensitive operations
result = await scrape_url("https://example.com", max_retries=1, timeout=10)
```

## Environment Variables

When running with Docker, you can configure the server using environment variables:

- `TRANSPORT`: Transport type (`streamable-http` or `sse`, default: `streamable-http`)
- `HOST`: Host to bind to (default: `0.0.0.0`)
- `PORT`: Port to bind to (default: `8000`)

## License

This project is licensed under the MIT License.

---

_Last updated: October 30, 2025_
