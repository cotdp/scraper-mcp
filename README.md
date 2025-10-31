# Scraper MCP

[![CI](https://github.com/cotdp/scraper-mcp/workflows/CI/badge.svg)](https://github.com/cotdp/scraper-mcp/actions/workflows/ci.yml)
[![Docker](https://github.com/cotdp/scraper-mcp/workflows/Build%20and%20Push%20Docker%20Images/badge.svg)](https://github.com/cotdp/scraper-mcp/actions/workflows/docker-publish.yml)
[![Docker Hub](https://img.shields.io/docker/v/cotdp/scraper-mcp?label=Docker%20Hub)](https://hub.docker.com/r/cotdp/scraper-mcp)
[![GHCR](https://img.shields.io/badge/GHCR-latest-blue)](https://github.com/cotdp/scraper-mcp/pkgs/container/scraper-mcp)

A context-optimized Model Context Protocol (MCP) server for efficient web scraping. This server provides AI tools with pre-processed, filtered web content—reducing token usage by converting raw HTML to markdown/text and applying CSS selectors server-side, so LLMs only receive the data they actually need.

## Instant Setup with Claude Code

Pull and run the pre-built image from Docker Hub:

```bash
# Using Docker Hub
docker run -d -p 8000:8000 --name scraper-mcp cotdp/scraper-mcp:latest

# Add the MCP server to Claude Code
claude mcp add --transport http scraper http://localhost:8000/mcp --scope user

# View logs
docker logs -f scraper-mcp

# Stop the server
docker stop scraper-mcp && docker rm scraper-mcp
```

Try it out in Claude Code:
```
> scrape https://cutler.sg/
~ scrapes the homepage, likely defaults to markdown conversion

> scrape and filter <url> elements from https://cutler.sg/sitemap.xml
~ returns about 100 urls

> scrape and filter all <title> elements from those urls
~ fetches only the titles from all ~100 urls
```

## Features

### Context Optimization
- **CSS selector filtering**: Extract only relevant content server-side (e.g., `.article-content`, `#main`) before sending to LLM
- **Smart conversion**: Transform HTML to markdown or plain text, eliminating markup noise
- **Link extraction**: Return structured link objects instead of raw HTML anchor tags
- **Targeted scraping**: Combine CSS selectors with strip_tags for precision filtering
- **Token efficiency**: Reduce context window usage by 70-90% compared to raw HTML

### Scraping Tools & Infrastructure
- **Multiple scraping modes**: Raw HTML, markdown conversion, plain text extraction, and link extraction
- **Batch operations**: Process multiple URLs concurrently with automatic retry logic
- **Intelligent caching**: Three-tier cache system (realtime/default/static) to minimize redundant requests
- **Retry & resilience**: Exponential backoff with configurable retries for transient failures
- **Provider architecture**: Extensible design supporting multiple scraping backends

### Monitoring & Management
- **Real-time dashboard**: Monitor server health, request statistics, cache metrics, and recent errors
- **Interactive playground**: Test scraping tools directly from your browser with live JSON responses
- **Runtime configuration**: Adjust concurrency, timeouts, retries, cache TTL, and proxy settings without restarts
- **Docker support**: One-command deployment with Docker Compose
- **HTTP/SSE transports**: Supports both Streamable HTTP and SSE MCP transports

## Dashboard Features

Access the monitoring dashboard at `http://localhost:8000/` to monitor and manage your scraper in real-time.

### Real-Time Monitoring Dashboard
Track server health, request statistics, retry metrics, and cache performance at a glance:

![Dashboard](docs/1-dashboard.png)

- **Server Status**: Health indicator, uptime, and start time
- **Request Statistics**: Total requests, success rate, and failure count
- **Retry Analytics**: Total retries and average per request
- **Cache Metrics**: Entry count, size, hit rate with one-click cache clearing
- **Recent Requests**: Last 10 requests with timestamps, status codes, and response times
- **Recent Errors**: Last 10 failures with detailed error messages and attempt counts
- Auto-refreshes every 9 seconds for real-time monitoring

### Interactive API Playground
Test all scraping tools without writing code:

![Playground](docs/2-playground.png)

- Test all four tools: `scrape_url`, `scrape_url_markdown`, `scrape_url_text`, `scrape_extract_links`
- Configure parameters: URL, timeout, max retries, CSS selectors
- View formatted JSON responses with syntax highlighting
- One-click copy to clipboard
- See execution time for performance testing

### Runtime Configuration
Adjust settings on-the-fly without restarting the server:

![Config](docs/3-config.png)

- **Performance Tuning**: Concurrency (1-50), timeout, max retries
- **Cache Control**: Default, realtime, and static cache TTL settings
- **Proxy Settings**: Enable/disable with HTTP/HTTPS/NO_PROXY configuration
- **Immediate Effect**: Changes apply instantly without server restart
- **Non-Persistent**: Settings reset on restart (use `.env` for permanent changes)

## Why Context-Friendly Scraping?

Traditional web scraping sends raw HTML to LLMs, wasting 70-90% of your context window on markup, scripts, and irrelevant content. Scraper MCP solves this by doing the heavy lifting server-side.

### Token Efficiency Comparison

**Without Filtering** (raw HTML):
```
❌ 45,000 tokens for a typical blog post
   - 40,000 tokens: HTML markup, CSS, JavaScript, ads, navigation
   - 5,000 tokens: actual article content
```

**With Scraper MCP** (CSS selector + markdown):
```
✅ 2,500 tokens for the same content
   - 0 tokens: markup eliminated by markdown conversion
   - 0 tokens: ads/navigation filtered by CSS selector
   - 2,500 tokens: clean article text
```

**Result**: 95% token reduction, 18x more content in the same context window

### Real-World Example

```python
# ❌ Traditional approach: Send raw HTML to LLM
html = requests.get("https://blog.example.com/article").text
# Result: 45KB of HTML → ~45,000 tokens

# ✅ Scraper MCP: Server-side filtering + conversion
scrape_url_markdown(
    "https://blog.example.com/article",
    css_selector="article.main-content"  # Extract only article
)
# Result: 2.5KB of markdown → ~2,500 tokens
```

### Key Benefits

1. **Massive Token Savings**: Reduce costs by 10-20x per request
2. **Larger Context Windows**: Fit 18x more content in the same context
3. **Faster Processing**: Less data to transfer and process
4. **Cleaner Data**: Pre-filtered, structured content ready for analysis
5. **Better Accuracy**: LLM focuses on relevant content, not markup noise

### When to Use Each Tool

- **`scrape_url_markdown`**: Articles, documentation, blog posts (best for LLM consumption)
- **`scrape_url_text`**: Plain text content, minimal formatting needed
- **`scrape_extract_links`**: Navigation, link analysis, sitemap generation
- **`scrape_url`** (raw HTML): When you need to preserve exact structure or extract meta tags

## Configuration

### Environment Setup

Create a `.env` file in the project root to configure the server. Copy from `.env.example`:

```bash
cp .env.example .env
```

#### Key Configuration Options

**Standard Proxy** (for corporate firewalls):
```bash
HTTP_PROXY=http://proxy.example.com:8080
HTTPS_PROXY=http://proxy.example.com:8080
NO_PROXY=localhost,127.0.0.1,.local
```

See [Proxy Configuration](#proxy-configuration) section for detailed setup instructions.

**ScrapeOps Proxy** (for JavaScript rendering, residential IPs, anti-bot):
```bash
SCRAPEOPS_API_KEY=your_api_key_here
SCRAPEOPS_RENDER_JS=true           # Enable for SPAs (default: false)
SCRAPEOPS_RESIDENTIAL=true         # Use residential proxies (default: false)
SCRAPEOPS_COUNTRY=us               # Target specific country (optional)
SCRAPEOPS_DEVICE=desktop           # Device type: desktop|mobile|tablet
```

See [ScrapeOps Proxy Integration](#scrapeops-proxy-integration) section for detailed setup, use cases, and cost optimization.

**Server Settings** (optional, defaults work for most cases):
```bash
TRANSPORT=streamable-http          # or 'sse'
HOST=0.0.0.0                       # Bind to all interfaces
PORT=8000                          # Default port
CACHE_DIR=/app/cache               # Cache directory path
ENABLE_CACHE_TOOLS=false           # Expose cache management tools
```

See `.env.example` for complete configuration reference with detailed comments.

## Quick Start

### Option 1: Docker Run (Simplest)

Pull and run the pre-built image from Docker Hub or GitHub Container Registry:

```bash
# Using Docker Hub
docker run -d -p 8000:8000 --name scraper-mcp cotdp/scraper-mcp:latest

# OR using GitHub Container Registry
docker run -d -p 8000:8000 --name scraper-mcp ghcr.io/cotdp/scraper-mcp:latest

# View logs
docker logs -f scraper-mcp

# Stop the server
docker stop scraper-mcp && docker rm scraper-mcp
```

The server will be available at:
- **MCP Endpoint**: `http://localhost:8000/mcp` (for AI clients)
- **Dashboard**: `http://localhost:8000/` (web interface)

### Option 2: Docker Compose (Recommended for Production)

For persistent storage, custom configuration, and easier management:

**1. Create a `docker-compose.yml` file:**

```yaml
services:
  scraper-mcp:
    image: cotdp/scraper-mcp:latest  # or ghcr.io/cotdp/scraper-mcp:latest
    container_name: scraper-mcp
    ports:
      - "8000:8000"
    environment:
      - TRANSPORT=streamable-http
      - HOST=0.0.0.0
      - PORT=8000
    volumes:
      - cache:/app/cache
    restart: unless-stopped

volumes:
  cache:
```

**2. (Optional) Create a `.env` file for proxy or ScrapeOps configuration:**

```bash
cp .env.example .env
# Edit .env with your proxy or ScrapeOps settings
```

**3. Start the server:**

```bash
# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f scraper-mcp

# Check status
docker-compose ps
```

**4. Stop the server:**

```bash
# Stop and remove containers
docker-compose down

# Stop, remove containers, and clear cache volume
docker-compose down -v
```

The server will be available at:
- **MCP Endpoint**: `http://localhost:8000/mcp` (for AI clients)
- **Dashboard**: `http://localhost:8000/` (web interface)

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

## Docker Images

### Pre-Built Images (Recommended)

Multi-platform images are automatically built and published on every release:

**Docker Hub:**
```bash
docker pull cotdp/scraper-mcp:latest
```

**GitHub Container Registry:**
```bash
docker pull ghcr.io/cotdp/scraper-mcp:latest
```

**Available tags:**
- `latest` - Latest stable release
- `0.1.0`, `0.1`, `0` - Semantic version tags
- `main-<sha>` - Latest main branch build

**Supported platforms:** `linux/amd64` and `linux/arm64`

See the [Quick Start](#quick-start) section for usage instructions.

### Building from Source

If you need to customize the image or build locally:

```bash
# Clone the repository
git clone https://github.com/cotdp/scraper-mcp.git
cd scraper-mcp

# Build the image
docker build -t scraper-mcp:custom .

# Run with default settings
docker run -p 8000:8000 scraper-mcp:custom

# Or use docker-compose.yml (modify image: line to use scraper-mcp:custom)
docker-compose up -d
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

Once connected, Claude can use all four scraping tools. You can monitor requests in real-time by opening `http://localhost:8000/` in your browser to access the dashboard.

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
│   │   └── requests_provider.py  # HTTP provider (requests library)
│   ├── core/
│   │   └── providers.py           # Provider registry and selection
│   ├── cache.py                   # Request caching (disk-based)
│   ├── cache_manager.py           # Cache lifecycle management
│   ├── metrics.py                 # Request/retry metrics tracking
│   └── utils.py                   # HTML processing utilities
├── tests/                         # Pytest test suite
│   ├── test_server.py
│   ├── test_tools.py
│   └── test_utils.py
├── .github/workflows/
│   ├── ci.yml                     # CI/CD: tests, linting
│   └── docker-publish.yml         # Docker image publishing
├── Dockerfile                     # Multi-stage production build
├── docker-compose.yml             # Local development setup
├── pyproject.toml                 # Python dependencies (uv)
├── .env.example                   # Environment configuration template
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

## Proxy Configuration

The scraper supports HTTP/HTTPS proxies through standard environment variables. This is useful when running behind a corporate firewall or when you need to route traffic through a specific proxy.

### Using Proxies with Docker Compose

Create a `.env` file in the project root (see `.env.example` for reference):

```bash
# HTTP proxy for non-SSL requests
HTTP_PROXY=http://proxy.example.com:8080
http_proxy=http://proxy.example.com:8080

# HTTPS proxy for SSL requests
HTTPS_PROXY=http://proxy.example.com:8080
https_proxy=http://proxy.example.com:8080

# Bypass proxy for specific hosts (comma-separated)
NO_PROXY=localhost,127.0.0.1,.local
no_proxy=localhost,127.0.0.1,.local
```

Then start the service:

```bash
docker-compose up -d
```

Docker Compose automatically reads `.env` files and passes variables to the container at both build time (for package installation) and runtime (for HTTP requests).

### Using Proxies with Docker Run

```bash
docker run -p 8000:8000 \
  -e HTTP_PROXY=http://proxy.example.com:8080 \
  -e HTTPS_PROXY=http://proxy.example.com:8080 \
  -e NO_PROXY=localhost,127.0.0.1,.local \
  scraper-mcp:latest
```

### Proxy with Authentication

If your proxy requires authentication, include credentials in the URL:

```bash
HTTP_PROXY=http://username:password@proxy.example.com:8080
HTTPS_PROXY=http://username:password@proxy.example.com:8080
```

### Build-Time vs Runtime Proxies

The proxy configuration works at two stages:

1. **Build time**: Used when Docker installs packages (apt, uv, pip)
2. **Runtime**: Used when the scraper makes HTTP requests

Both uppercase and lowercase variable names are supported (e.g., `HTTP_PROXY` and `http_proxy`).

### Verifying Proxy Configuration

Check the container logs to verify proxy settings are being used:

```bash
docker-compose logs scraper-mcp
```

The `requests` library automatically respects these environment variables and will route all HTTP/HTTPS traffic through the configured proxy.

## ScrapeOps Proxy Integration

The scraper includes optional integration with [ScrapeOps](https://scrapeops.io/), a premium proxy service that helps bypass anti-bot measures, render JavaScript, and access geo-restricted content. ScrapeOps automatically enables when an API key is provided.

### What is ScrapeOps?

ScrapeOps provides:
- **JavaScript rendering**: Scrape SPAs and dynamic content
- **Residential proxies**: Less likely to be blocked
- **Geo-targeting**: Access content from specific countries
- **Anti-bot bypass**: Automatic header rotation and fingerprinting
- **High success rate**: Smart retry and optimization

### Enabling ScrapeOps

Simply add your API key to the `.env` file:

```bash
# Get your API key from https://scrapeops.io/
SCRAPEOPS_API_KEY=your_api_key_here
```

That's it! All scraping requests will automatically route through ScrapeOps. No changes needed to your MCP tools or code.

### Configuration Options

Customize ScrapeOps behavior with environment variables (see `.env.example` for full reference):

```bash
# Enable JavaScript rendering for SPAs (default: false)
SCRAPEOPS_RENDER_JS=true

# Use residential proxies instead of datacenter (default: false)
SCRAPEOPS_RESIDENTIAL=true

# Target specific country (optional)
SCRAPEOPS_COUNTRY=us

# Keep original headers instead of optimizing (default: false)
SCRAPEOPS_KEEP_HEADERS=true

# Device type for user agent rotation (default: desktop)
SCRAPEOPS_DEVICE=mobile
```

### Full Example Configuration

```bash
# .env file
SCRAPEOPS_API_KEY=your_api_key_here
SCRAPEOPS_RENDER_JS=true
SCRAPEOPS_RESIDENTIAL=true
SCRAPEOPS_COUNTRY=us
SCRAPEOPS_DEVICE=desktop
```

## License

This project is licensed under the MIT License.

---

_Last updated: October 31, 2025_
