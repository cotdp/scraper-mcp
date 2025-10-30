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

**Returns:**
- `url`: Final URL after redirects
- `content`: Raw HTML content
- `status_code`: HTTP status code
- `content_type`: Content-Type header value
- `metadata`: Additional metadata (headers, encoding, elapsed time)

### 2. `scrape_url_markdown`
Scrape a URL and convert the content to markdown format.

**Parameters:**
- `url` (string, required): The URL to scrape
- `timeout` (integer, optional): Request timeout in seconds (default: 30)
- `strip_tags` (array, optional): List of HTML tags to strip (e.g., ['script', 'style'])

**Returns:**
- Same as `scrape_url` but with markdown-formatted content
- `metadata.page_metadata`: Extracted page metadata (title, description, etc.)

### 3. `scrape_url_text`
Scrape a URL and extract plain text content.

**Parameters:**
- `url` (string, required): The URL to scrape
- `timeout` (integer, optional): Request timeout in seconds (default: 30)
- `strip_tags` (array, optional): HTML tags to strip (default: script, style, meta, link, noscript)

**Returns:**
- Same as `scrape_url` but with plain text content
- `metadata.page_metadata`: Extracted page metadata

### 4. `scrape_extract_links`
Scrape a URL and extract all links.

**Parameters:**
- `url` (string, required): The URL to scrape
- `timeout` (integer, optional): Request timeout in seconds (default: 30)

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

## Environment Variables

When running with Docker, you can configure the server using environment variables:

- `TRANSPORT`: Transport type (`streamable-http` or `sse`, default: `streamable-http`)
- `HOST`: Host to bind to (default: `0.0.0.0`)
- `PORT`: Port to bind to (default: `8000`)

## License

This project is licensed under the MIT License.

---

_Last updated: October 30, 2025_
