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
- `urls` (string or list, required): Single URL or list of URLs to scrape (http:// or https://)
- `timeout` (integer, optional): Request timeout in seconds (default: 30)
- `max_retries` (integer, optional): Maximum retry attempts on failure (default: 3)
- `css_selector` (string, optional): CSS selector to filter HTML elements (e.g., "meta", "img, video", ".article-content")

**Returns:**
- `url`: Final URL after redirects
- `content`: Raw HTML content (filtered if css_selector provided)
- `status_code`: HTTP status code
- `content_type`: Content-Type header value
- `metadata`: Additional metadata including:
  - `headers`: Response headers
  - `encoding`: Content encoding
  - `elapsed_ms`: Request duration in milliseconds
  - `attempts`: Total number of attempts made
  - `retries`: Number of retries performed
  - `css_selector_applied`: CSS selector used (if provided)
  - `elements_matched`: Number of elements matched (if css_selector provided)

### 2. `scrape_url_markdown`
Scrape a URL and convert the content to markdown format.

**Parameters:**
- `urls` (string or list, required): Single URL or list of URLs to scrape (http:// or https://)
- `timeout` (integer, optional): Request timeout in seconds (default: 30)
- `max_retries` (integer, optional): Maximum retry attempts on failure (default: 3)
- `strip_tags` (array, optional): List of HTML tags to strip (e.g., ['script', 'style'])
- `css_selector` (string, optional): CSS selector to filter HTML before conversion (e.g., ".article-content", "article p")

**Returns:**
- Same as `scrape_url` but with markdown-formatted content
- `metadata.page_metadata`: Extracted page metadata (title, description, etc.)
- `metadata.attempts`: Total number of attempts made
- `metadata.retries`: Number of retries performed
- `metadata.css_selector_applied` and `metadata.elements_matched` (if css_selector provided)

### 3. `scrape_url_text`
Scrape a URL and extract plain text content.

**Parameters:**
- `urls` (string or list, required): Single URL or list of URLs to scrape (http:// or https://)
- `timeout` (integer, optional): Request timeout in seconds (default: 30)
- `max_retries` (integer, optional): Maximum retry attempts on failure (default: 3)
- `strip_tags` (array, optional): HTML tags to strip (default: script, style, meta, link, noscript)
- `css_selector` (string, optional): CSS selector to filter HTML before text extraction (e.g., "#main-content", "article.post")

**Returns:**
- Same as `scrape_url` but with plain text content
- `metadata.page_metadata`: Extracted page metadata
- `metadata.attempts`: Total number of attempts made
- `metadata.retries`: Number of retries performed
- `metadata.css_selector_applied` and `metadata.elements_matched` (if css_selector provided)

### 4. `scrape_extract_links`
Scrape a URL and extract all links.

**Parameters:**
- `urls` (string or list, required): Single URL or list of URLs to scrape (http:// or https://)
- `timeout` (integer, optional): Request timeout in seconds (default: 30)
- `max_retries` (integer, optional): Maximum retry attempts on failure (default: 3)
- `css_selector` (string, optional): CSS selector to scope link extraction to specific sections (e.g., "nav", "article.main-content")

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

## CSS Selector Filtering

All scraping tools support optional CSS selector filtering to extract specific elements from HTML before processing. This allows you to focus on exactly the content you need.

### Supported Selectors

The server uses BeautifulSoup4's `.select()` method (powered by Soup Sieve), supporting:

- **Tag selectors**: `meta`, `img`, `a`, `div`
- **Multiple selectors**: `img, video` (comma-separated)
- **Class selectors**: `.article-content`, `.main-text`
- **ID selectors**: `#header`, `#main-content`
- **Attribute selectors**: `a[href]`, `meta[property="og:image"]`, `img[src^="https://"]`
- **Descendant combinators**: `article p`, `div.content a`
- **Pseudo-classes**: `p:nth-of-type(3)`, `a:not([rel])`

### Usage Examples

```python
# Extract only meta tags for SEO analysis
scrape_url("https://example.com", css_selector="meta")

# Get article content as markdown, excluding ads
scrape_url_markdown("https://blog.com/article", css_selector="article.main-content")

# Extract text from specific section
scrape_url_text("https://example.com", css_selector="#main-content")

# Get only product images
scrape_url("https://shop.com/product", css_selector="img.product-image, img[data-product]")

# Extract only navigation links
scrape_extract_links("https://example.com", css_selector="nav.primary")

# Get Open Graph meta tags
scrape_url("https://example.com", css_selector='meta[property^="og:"]')

# Combine with strip_tags for fine-grained control
scrape_url_markdown(
    "https://example.com",
    css_selector="article",  # First filter to article
    strip_tags=["script", "style"]  # Then remove scripts and styles
)
```

### How It Works

1. **Scrape**: Fetch HTML from the URL
2. **Filter** (if `css_selector` provided): Apply CSS selector to keep only matching elements
3. **Process**: Convert to markdown/text or extract links
4. **Return**: Include `elements_matched` count in metadata

### CSS Selector Benefits

- **Reduce noise**: Extract only relevant content, ignoring ads, navigation, footers
- **Scoped extraction**: Get links only from specific sections (e.g., main content, not sidebar)
- **Efficient**: Process less HTML, get cleaner results
- **Composable**: Works alongside `strip_tags` for maximum control

## Environment Variables

When running with Docker, you can configure the server using environment variables:

- `TRANSPORT`: Transport type (`streamable-http` or `sse`, default: `streamable-http`)
- `HOST`: Host to bind to (default: `0.0.0.0`)
- `PORT`: Port to bind to (default: `8000`)
- `ENABLE_CACHE_TOOLS`: Enable cache management tools (`true`, `1`, or `yes` to enable, default: `false`)
  - When enabled, exposes `cache_stats`, `cache_clear_expired`, and `cache_clear_all` tools
  - Disabled by default for security and simplicity

## License

This project is licensed under the MIT License.

---

_Last updated: October 30, 2025_
