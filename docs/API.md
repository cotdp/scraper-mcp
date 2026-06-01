# API Reference

Complete documentation for all Scraper MCP tools.

## Available Tools

### 1. `scrape_url`

Scrape raw HTML content from a URL.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `urls` | string or list | Yes | - | Single URL or list of URLs (http:// or https://) |
| `timeout` | integer | No | 30 | Request timeout in seconds |
| `max_retries` | integer | No | 3 | Maximum retry attempts on failure |
| `css_selector` | string | No | - | CSS selector to filter HTML elements |

**Returns:**
- `url`: Final URL after redirects
- `content`: Raw HTML content (filtered if css_selector provided)
- `status_code`: HTTP status code
- `content_type`: Content-Type header value
- `metadata`: Object containing `headers`, `encoding`, `elapsed_ms`, `attempts`, `retries`, `css_selector_applied`, `elements_matched`

---

### 2. `scrape_url_markdown`

Scrape a URL and convert the content to markdown format. Best for LLM consumption.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `urls` | string or list | Yes | - | Single URL or list of URLs |
| `timeout` | integer | No | 30 | Request timeout in seconds |
| `max_retries` | integer | No | 3 | Maximum retry attempts |
| `strip_tags` | array | No | - | HTML tags to strip (e.g., `['script', 'style']`) |
| `css_selector` | string | No | - | CSS selector to filter HTML before conversion |

**Returns:**
- Same as `scrape_url` but with markdown-formatted content
- `metadata.page_metadata`: Extracted page metadata (title, description, etc.)

---

### 3. `scrape_url_text`

Scrape a URL and extract plain text content.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `urls` | string or list | Yes | - | Single URL or list of URLs |
| `timeout` | integer | No | 30 | Request timeout in seconds |
| `max_retries` | integer | No | 3 | Maximum retry attempts |
| `strip_tags` | array | No | script, style, meta, link, noscript | HTML tags to strip |
| `css_selector` | string | No | - | CSS selector to filter HTML before extraction |

**Returns:**
- Same as `scrape_url` but with plain text content

---

### 4. `scrape_extract_links`

Scrape a URL and extract all links.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `urls` | string or list | Yes | - | Single URL or list of URLs |
| `timeout` | integer | No | 30 | Request timeout in seconds |
| `max_retries` | integer | No | 3 | Maximum retry attempts |
| `css_selector` | string | No | - | CSS selector to scope link extraction |

**Returns:**
- `url`: The URL that was scraped
- `links`: Array of link objects with `url`, `text`, and `title`
- `count`: Total number of links found

---

### 5. `perplexity`

Search the web using Perplexity AI. Requires `PERPLEXITY_API_KEY` environment variable.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `messages` | array | Yes | - | Conversation messages with `role` and `content` |
| `model` | string | No | sonar | Model name. Only enabled (opt-in) models are accepted — see note below |
| `temperature` | number | No | 0.3 | Creativity 0-2 (lower = focused) |
| `max_tokens` | integer | No | 4000 | Maximum response length |

> **Model allowlist:** Only `sonar` is enabled by default. `sonar-pro`,
> `sonar-reasoning`, `sonar-reasoning-pro`, and `sonar-deep-research` must be
> enabled (opt-in) via `PERPLEXITY_ENABLED_MODELS` or the `perplexity_enabled_models`
> runtime config. A disabled model returns an error without making an API call.
> See [CONFIGURATION.md](CONFIGURATION.md#model-allowlist-opt-in).

**Returns:**
- `content`: AI-generated response with citation markers
- `model`: Model used
- `citations`: Array of source URLs
- `usage`: Token usage statistics

---

### 6. `perplexity_reason`

Complex reasoning tasks using Perplexity's reasoning model (`sonar-reasoning-pro`).
Requires `PERPLEXITY_API_KEY`.

> **Disabled by default:** `sonar-reasoning-pro` is opt-in, so this tool returns a
> "model not enabled" error until you enable it via `PERPLEXITY_ENABLED_MODELS` or
> the `perplexity_enabled_models` runtime config.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | - | The query or problem to reason about |
| `temperature` | number | No | 0.3 | Creativity 0-2 |
| `max_tokens` | integer | No | 4000 | Maximum response length |

**Returns:**
- Same as `perplexity` tool

---

## CSS Selector Filtering

All scraping tools support CSS selector filtering to extract specific elements before processing.

### Supported Selectors

The server uses BeautifulSoup4's `.select()` method (Soup Sieve), supporting:

| Selector Type | Example | Description |
|---------------|---------|-------------|
| Tag | `meta`, `img`, `a` | Select by tag name |
| Multiple | `img, video` | Comma-separated |
| Class | `.article-content` | Select by class |
| ID | `#main-content` | Select by ID |
| Attribute | `a[href]`, `meta[property="og:image"]` | Select by attribute |
| Descendant | `article p`, `div.content a` | Nested selectors |
| Pseudo-class | `p:nth-of-type(3)`, `a:not([rel])` | Advanced filtering |

### Examples

```python
# Extract only meta tags
scrape_url("https://example.com", css_selector="meta")

# Get article content as markdown
scrape_url_markdown("https://blog.com/article", css_selector="article.main-content")

# Extract text from specific section
scrape_url_text("https://example.com", css_selector="#main-content")

# Get only navigation links
scrape_extract_links("https://example.com", css_selector="nav.primary")

# Get Open Graph meta tags
scrape_url("https://example.com", css_selector='meta[property^="og:"]')

# Combine with strip_tags
scrape_url_markdown(
    "https://example.com",
    css_selector="article",
    strip_tags=["script", "style"]
)
```

### How It Works

1. **Scrape**: Fetch HTML from the URL
2. **Filter**: Apply CSS selector to keep only matching elements
3. **Process**: Convert to markdown/text or extract links
4. **Return**: Include `elements_matched` count in metadata

---

## Retry Behavior

The scraper includes intelligent retry logic with exponential backoff.

### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `max_retries` | 3 | Maximum retry attempts |
| `timeout` | 30s | Request timeout |
| Retry delay | 1s initial | Exponential backoff |

### Retry Schedule

For default configuration (max_retries=3):

1. **First attempt**: Immediate
2. **Retry 1**: Wait 1 second
3. **Retry 2**: Wait 2 seconds
4. **Retry 3**: Wait 4 seconds

Total maximum wait: ~7 seconds before final failure.

### What Triggers Retries

- Network timeouts
- Connection failures
- HTTP errors (4xx, 5xx status codes)

### Response Metadata

All responses include retry information:

```json
{
  "attempts": 2,
  "retries": 1,
  "elapsed_ms": 234.5
}
```

### Customizing Retries

```python
# Disable retries
scrape_url("https://example.com", max_retries=0)

# More aggressive retries
scrape_url("https://example.com", max_retries=5, timeout=60)

# Quick fail
scrape_url("https://example.com", max_retries=1, timeout=10)
```

---

## Batch Operations

All tools support batch operations by passing a list of URLs:

```python
# Single URL
scrape_url("https://example.com")

# Batch operation
scrape_url(["https://example.com", "https://example.org", "https://example.net"])
```

Batch operations:
- Execute concurrently (default: 5 parallel requests)
- Return results for all URLs with individual success/failure status
- Include totals: `total`, `successful`, `failed`

---

## Resources

MCP resources provide read-only data access via URI-based addressing. Access resources via `resources/list` and `resources/read`.

### Cache Resources

| URI | Description |
|-----|-------------|
| `cache://stats` | Cache statistics (hit rate, size, entries) |
| `cache://requests` | List of recent request IDs with metadata |
| `cache://request/{id}` | Full cached result by request ID |
| `cache://request/{id}/content` | Just the content from a cached request |
| `cache://request/{id}/metadata` | Just the metadata from a cached request |

### Configuration Resources

| URI | Description |
|-----|-------------|
| `config://current` | Current runtime configuration (API key masked) |
| `config://defaults` | Default configuration values |
| `config://scraping` | Scraping settings (timeout, retries, concurrency) |
| `config://cache` | Cache settings (TTLs, directory) |
| `config://perplexity` | Perplexity settings (enabled/available models, key status) |

### Server Resources

| URI | Description |
|-----|-------------|
| `server://info` | Server info (version, uptime, capabilities) |
| `server://metrics` | Request metrics (counts, success rates) |
| `server://tools` | List of available tools with descriptions |

---

## Prompts

MCP prompts provide reusable, parameterized workflow templates. Access prompts via `prompts/list` and `prompts/get`.

### Content Analysis Prompts

| Prompt | Parameters | Purpose |
|--------|------------|---------|
| `analyze_webpage` | `url`, `focus` | Structured webpage analysis |
| `summarize_content` | `url`, `length`, `style` | Generate content summaries |
| `extract_data` | `url`, `data_type`, `selector` | Extract specific data types |
| `compare_pages` | `urls` | Compare multiple pages |

### SEO/Technical Prompts

| Prompt | Parameters | Purpose |
|--------|------------|---------|
| `seo_audit` | `url` | Comprehensive SEO check |
| `link_audit` | `url` | Analyze internal/external links |
| `metadata_check` | `url` | Review meta tags and OG data |
| `accessibility_check` | `url` | Basic accessibility analysis |

### Research Prompts

| Prompt | Parameters | Purpose |
|--------|------------|---------|
| `research_topic` | `topic`, `depth` | Multi-source research |
| `fact_check` | `claim`, `sources` | Verify claims |
| `competitive_analysis` | `urls` | Compare competitors |
| `news_roundup` | `topic`, `timeframe` | Gather recent news |

### Disabling Resources/Prompts

To reduce context overhead:

```bash
# Environment variables
DISABLE_RESOURCES=true
DISABLE_PROMPTS=true

# CLI flags
python -m scraper_mcp --disable-resources --disable-prompts
```
