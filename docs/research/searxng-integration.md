# SearXNG Integration Research

## Executive Summary

SearXNG is a free, open-source metasearch engine that aggregates results from 70+ search engines without tracking users. It exposes a simple JSON API (`/search?q=...&format=json`) that requires no authentication. Running it as a Docker sidecar alongside the existing scraper-mcp service would add **native web search** capabilities — a fundamentally new tool category (search) alongside the existing scrape/extract tools and the Perplexity AI tools.

This document covers the API surface, integration architecture, Docker sidecar setup, and identifies gaps that would need to be addressed.

---

## 1. SearXNG API Surface

### Endpoint
```
GET/POST /search?q={query}&format=json
```

### Request Parameters

| Parameter     | Type   | Default    | Description                                                    |
|---------------|--------|------------|----------------------------------------------------------------|
| `q`           | string | (required) | Search query                                                   |
| `format`      | string | `html`     | Response format — must be `json` for API use                   |
| `categories`  | string | `general`  | Comma-separated: `general`, `images`, `videos`, `news`, `it`, `science`, `files`, `social media`, `music` |
| `engines`     | string | (all)      | Comma-separated engine names: `google`, `bing`, `duckduckgo`, etc. |
| `language`    | string | `all`      | ISO 639-1 code (e.g., `en`, `fr`)                             |
| `pageno`      | int    | `1`        | Page number for pagination                                     |
| `time_range`  | string | (none)     | `day`, `week`, `month`, `year`                                 |
| `safesearch`  | int    | `0`        | `0` = off, `1` = moderate, `2` = strict                       |

### Response Format (JSON)

```json
{
  "query": "search terms",
  "number_of_results": 42,
  "results": [
    {
      "title": "Result Title",
      "url": "https://example.com/page",
      "content": "Snippet/description text...",
      "engine": "google",
      "parsed_url": ["https", "example.com", "/page", "", "", ""],
      "engines": ["google", "bing"],
      "positions": [1, 3],
      "score": 5.0,
      "category": "general"
    }
  ],
  "infoboxes": [
    {
      "infobox": "Topic Name",
      "id": "https://en.wikipedia.org/wiki/...",
      "content": "Summary paragraph...",
      "urls": [{"title": "Wikipedia", "url": "..."}],
      "engine": "wikipedia"
    }
  ],
  "suggestions": ["related query 1", "related query 2"],
  "corrections": ["corrected spelling"],
  "unresponsive_engines": [["engine_name", "error message"]]
}
```

**Category-specific result fields:**
- **Images**: `thumbnail_src`, `img_src`, `resolution`, `img_format`, `filesize`
- **Videos**: `thumbnail`, `length`, `publishedDate`, `iframe_src`
- **News**: `publishedDate`, `thumbnail`

### Key Characteristics
- **No authentication required** — fully open API
- **JSON format must be explicitly enabled** in `settings.yml` (`search.formats: [json]`)
- **No rate limiting by default** — must be configured in settings
- **Aggregates and deduplicates** results across engines, assigning a merged `score`
- **No API versioning** — response format tied to SearXNG version

---

## 2. Docker Sidecar Architecture

### Proposed docker-compose.yml Addition

```yaml
services:
  scraper-mcp:
    # ... existing service ...
    depends_on:
      searxng:
        condition: service_healthy
    environment:
      - SEARXNG_BASE_URL=http://searxng:8080
    networks:
      - mcp-network

  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    volumes:
      - ./searxng/settings.yml:/etc/searxng/settings.yml:ro
      - searxng_data:/var/cache/searxng
    environment:
      - SEARXNG_SECRET=<generated-secret>
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
    networks:
      - mcp-network
    # NOT exposed to host — only accessible within Docker network
    # ports:
    #   - "127.0.0.1:8080:8080"  # Uncomment for debugging

volumes:
  searxng_data:
    driver: local
```

### Minimal settings.yml for API-only Use

```yaml
use_default_settings: true

server:
  secret_key: "generate-with-openssl-rand-hex-32"
  limiter: false  # Internal sidecar, no public exposure
  image_proxy: false

search:
  formats:
    - json
  # Disable HTML to discourage UI use (optional)
  # - html

engines:
  # Disable engines that require API keys or are unreliable
  - name: google
    disabled: false
  - name: bing
    disabled: false
  - name: duckduckgo
    disabled: false
  - name: wikipedia
    disabled: false
  - name: github
    disabled: false
  - name: stackoverflow
    disabled: false
```

### Resource Considerations
- **Memory**: 256-512 MB typical for API-only use
- **CPU**: Minimal — SearXNG proxies queries to external engines
- **Storage**: Small cache volume for search results
- **Network**: Outbound HTTP to search engines; inbound only from scraper-mcp on Docker network
- **Startup**: ~5-10 seconds cold start

---

## 3. Integration with Existing Architecture

### How It Maps to the Current Codebase

The project has two distinct integration patterns:

1. **Provider pattern** (`providers/base.py` -> `ScraperProvider`): For URL-based scraping with `scrape(url)` interface
2. **Service pattern** (`services/perplexity_service.py` -> `PerplexityService`): For API-based external services

SearXNG integration should follow the **Service pattern** (like Perplexity), not the Provider pattern, because:
- Search is a fundamentally different operation than scraping (query-in, results-out vs URL-in, content-out)
- It doesn't fit the `ScraperProvider.scrape(url)` interface
- It aligns with how Perplexity tools are structured: service class + Pydantic models + tool registration

### Proposed File Structure

```
src/scraper_mcp/
  services/
    searxng_service.py          # SearXNG API client (like perplexity_service.py)
  models/
    search.py                   # SearchResult, SearchResponse, BatchSearchResponse models
  tools/
    router.py                   # Add register_search_tools() function
```

### Proposed Pydantic Models

```python
class SearchResult(BaseModel):
    """A single search result."""
    title: str
    url: str
    content: str  # snippet/description
    engine: str
    engines: list[str] = []
    score: float = 0.0
    category: str = "general"
    # Category-specific optional fields
    thumbnail: str | None = None
    published_date: str | None = None

class SearchResponse(BaseModel):
    """Response from a search query."""
    query: str
    results: list[SearchResult]
    total_results: int
    suggestions: list[str] = []
    corrections: list[str] = []
    infoboxes: list[dict[str, Any]] = []
    unresponsive_engines: list[list[str]] = []
    metadata: dict[str, Any] = {}  # elapsed_ms, engines_used, etc.
```

### Proposed MCP Tools

| Tool Name        | Parameters                                    | Return Type      | Description                         |
|------------------|-----------------------------------------------|------------------|-------------------------------------|
| `search`         | `query`, `categories?`, `language?`, `time_range?`, `safesearch?`, `max_results?`, `pageno?`, `engines?` | `SearchResponse` | Web search via SearXNG              |
| `search_news`    | `query`, `language?`, `time_range?`, `max_results?` | `SearchResponse` | News-specific search (sugar for `categories=news`) |
| `search_images`  | `query`, `language?`, `safesearch?`, `max_results?` | `SearchResponse` | Image search (sugar for `categories=images`) |

### Registration Pattern (following Perplexity precedent)

```python
# In server.py
if SearxngService.is_available():
    register_search_tools(mcp)

# In tools/router.py
def register_search_tools(mcp: FastMCP) -> None:
    mcp.tool()(search)
    mcp.tool()(search_news)
    mcp.tool()(search_images)
```

---

## 4. Identified Gaps and Challenges

### 4.1 Architectural Gaps

| Gap | Description | Severity | Notes |
|-----|-------------|----------|-------|
| **New model layer** | Need `models/search.py` with result types that don't exist yet — search results are structurally different from scrape results | Medium | Follow `models/perplexity.py` pattern |
| **No search-specific caching** | Existing `diskcache` is tuned for HTML responses; search results have different TTL needs (shorter for news, longer for general) | Medium | Could reuse cache infra with different TTL policies |
| **No result count limiting** | SearXNG returns all aggregated results; need a `max_results` param to truncate for context-efficiency | Low | Simple slice on results array |
| **Metrics integration** | `record_request()` currently expects URL-based metrics; search queries need a `request_type="search"` variant | Low | Extend existing metrics pattern |
| **Health monitoring** | Need to check SearXNG sidecar health from scraper-mcp, not just its own health | Medium | Add SearXNG health to `/healthz` endpoint |
| **Dashboard integration** | Existing admin dashboard would need a "Search" section for search metrics | Low | Enhancement, not blocker |

### 4.2 Configuration Gaps

| Gap | Description | Mitigation |
|-----|-------------|------------|
| **Engine configuration** | Users will want to customize which engines are active | Ship a sensible default `settings.yml`, document customization |
| **Secret management** | SearXNG requires `secret_key` | Auto-generate on first run or use env var |
| **SearXNG URL discovery** | Scraper-mcp needs to know SearXNG's address | `SEARXNG_BASE_URL` env var, default to `http://searxng:8080` |
| **Optional dependency** | SearXNG sidecar should be optional (like Perplexity) | Guard with `is_available()` check + env var |
| **JSON format must be enabled** | Default SearXNG settings don't enable JSON API | Ship custom `settings.yml` with JSON enabled |

### 4.3 Operational Gaps

| Gap | Description | Impact |
|-----|-------------|--------|
| **Cold start latency** | SearXNG takes 5-10s to start; first queries may fail | Use `depends_on: condition: service_healthy` + retry logic |
| **Engine reliability** | Some engines may be rate-limited or blocked from data center IPs | Configure fallback engines; expose `unresponsive_engines` in response |
| **No built-in rate limiting** | If SearXNG is exposed or heavily used, it can overload upstream engines | Configure `server.limiter` in settings.yml; add app-level rate limiting |
| **Version pinning** | Using `searxng/searxng:latest` risks breaking changes | Pin to specific version tag |
| **Storage growth** | SearXNG cache can grow unbounded | Set cache volume limits or periodic cleanup |

### 4.4 Feature Gaps vs. Perplexity

| Feature | Perplexity | SearXNG | Gap? |
|---------|-----------|---------|------|
| AI-synthesized answers | Yes | No | Yes — SearXNG returns raw search results, no AI synthesis |
| Citations with context | Yes | Partial (URLs only, no inline citations) | Yes — no citation-to-content mapping |
| Reasoning/analysis | Yes (sonar-reasoning-pro) | No | Yes — fundamentally different: search vs. AI |
| Web search | Yes (built into AI response) | Yes (direct search results) | No |
| Cost | Per-token API charges | Free (self-hosted) | Advantage SearXNG |
| Privacy | Data sent to Perplexity | Queries proxied through self-hosted instance | Advantage SearXNG |
| Offline/air-gapped | No | Partial (needs internet for engines, but self-hosted) | Advantage SearXNG |
| Customizable engines | No | Full control | Advantage SearXNG |
| Image/video search | No | Yes | Advantage SearXNG |
| News-specific search | No | Yes (dedicated category) | Advantage SearXNG |

**Key insight**: SearXNG and Perplexity are **complementary, not competing**. SearXNG provides raw search results (good for agents that need URLs to scrape), while Perplexity provides AI-synthesized answers. An agent workflow could: (1) search via SearXNG, (2) scrape top results, (3) use Perplexity for synthesis.

### 4.5 Interface Consistency Gaps

The existing tools follow a **batch-first, URL-based** pattern:
```python
# Existing: takes URLs, returns batch response
scrape_url(urls: list[str], ...) -> BatchScrapeResponse
```

A search tool is fundamentally **query-based, single-invocation**:
```python
# New: takes a query string, returns search results
search(query: str, ...) -> SearchResponse
```

This is a natural divergence (search and scrape are different operations), but to maintain consistency:
- Response models should follow the same patterns (Pydantic BaseModel, metadata dict, success/error handling)
- The tool should integrate with the same metrics/dashboard infrastructure
- Error handling should follow the same patterns as PerplexityService

There is **no need** to force search into the batch scrape pattern — the Perplexity tools already established a precedent for non-batch, non-URL tools.

---

## 5. Comparison: SearXNG vs. Alternatives

| Criteria | SearXNG | Google Custom Search | Brave Search API | Tavily |
|----------|---------|---------------------|------------------|--------|
| Cost | Free (self-hosted) | $5/1000 queries | Free tier + paid | $0.01/query |
| Privacy | Full control | Google collects data | Brave collects data | Tavily collects data |
| Setup complexity | Medium (Docker sidecar) | Low (API key) | Low (API key) | Low (API key) |
| Result quality | Good (aggregated) | Excellent | Good | Good (AI-optimized) |
| Customization | Full (engine selection) | Limited | Limited | Limited |
| Rate limits | Self-managed | 100/day free | 2000/month free | Varies by plan |
| AI synthesis | No | No | No | Yes |
| Maintenance burden | Medium (updates, engine config) | None | None | None |
| Offline capability | Self-hosted infrastructure | No | No | No |

**Recommendation**: SearXNG is the best fit for this project because:
1. Aligns with the self-hosted, privacy-focused philosophy
2. Zero marginal cost per query
3. Full customization of engines and categories
4. Natural fit as a Docker sidecar (already uses Docker)
5. Existing community patterns for agentic AI use (AG2, LangChain, LiteLLM integrations)

---

## 6. Implementation Estimate

### Minimal viable integration:
1. `searxng/settings.yml` — default configuration file
2. `docker-compose.yml` update — add SearXNG sidecar service
3. `models/search.py` — Pydantic models for search results
4. `services/searxng_service.py` — HTTP client for SearXNG API
5. `tools/router.py` — register `search` tool
6. `server.py` — conditional registration (like Perplexity)
7. Tests

### Optional enhancements:
- `search_news` / `search_images` convenience tools
- Search result caching with appropriate TTLs
- Dashboard integration for search metrics
- Combine search + scrape workflow tool
- SearXNG health in `/healthz` aggregate

---

## 7. Open Questions

1. **Should search results be cached?** The existing diskcache infra could be reused, but search results have different freshness requirements than scraped pages.

2. **Should we provide a "search and scrape" compound tool?** An agent-friendly tool that searches, then scrapes the top N results would be powerful but adds complexity.

3. **How to handle SearXNG being unavailable?** Follow the Perplexity pattern (`is_available()` check) — but SearXNG could go down at runtime (unlike Perplexity which is "available or not" at startup based on API key).

4. **Should the SearXNG UI be accessible?** It could be useful for debugging but adds security surface. Recommend keeping it internal-only (no port binding to host by default).

5. **Engine selection at query time vs. config time?** The `engines` parameter could be exposed as a tool parameter, but this might be overwhelming for AI agents. Consider defaulting to a curated set and allowing override.
