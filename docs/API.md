# API Reference

The default transport is Streamable HTTP at `http://127.0.0.1:8000/mcp`.
The CLI also supports SSE. It does not expose a stdio transport option.
Use MCP discovery (`tools/list`) for the running server's exact tool schemas.

MCP clients must be trusted: the administrative token does not authenticate MCP
requests. The dashboard and every `/api/*` route require `SCRAPER_ADMIN_TOKEN`;
`/healthz` is public. See [Security](../SECURITY.md).

## Scraping tools

All four tools require `urls` as a **list of strings**, including for one URL.
They always return a batch envelope. There is no `scrape_url_markdown` tool.

| Tool | Result content | Additional parameter |
|------|----------------|----------------------|
| `scrape_url` | Markdown | `strip_tags: list[str] \| null` |
| `scrape_url_html` | Raw HTML | None |
| `scrape_url_text` | Plain text | `strip_tags: list[str] \| null` |
| `scrape_extract_links` | Link objects | None |

The common parameters are:

| Parameter | Type | Default | Meaning |
|-----------|------|---------|---------|
| `urls` | `list[str]` | Required | HTTP or HTTPS URLs |
| `timeout` | Integer | `30` | Timeout for each request, in seconds |
| `max_retries` | Integer | `3` | Retries after the initial attempt; `0` disables retries |
| `css_selector` | String or null | `null` | Keep matching HTML elements before conversion |
| `include_headers` | Boolean | `false` | Include HTTP headers in scrape metadata |
| `render_js` | Boolean | `false` | Render with Playwright/Chromium before extraction |

`strip_tags` removes the named elements after selector filtering. Markdown applies
no extra tag-removal list unless requested. Plain text removes `script`, `style`,
`meta`, `link`, and `noscript` by default. Playwright requires its optional package
and Chromium installation; the production image includes both.

Calls process batches concurrently with a limit of eight at the tool layer.
Playwright separately limits active browser contexts. Results retain input order.

### Scrape response

`scrape_url`, `scrape_url_html`, and `scrape_url_text` return this structure:

```json
{
  "total": 1,
  "successful": 1,
  "failed": 0,
  "results": [
    {
      "url": "https://example.com/",
      "success": true,
      "data": {
        "content": "# Example Domain",
        "status_code": 200,
        "content_type": "text/html",
        "metadata": {"elapsed_ms": 42.0}
      },
      "error": null
    }
  ]
}
```

Each item identifies the requested URL. On an individual failure, `success` is
`false`, `data` is `null`, and `error` describes the failure. Check `failed` and
individual results even when the MCP call itself succeeds. Invalid arguments or
provider selection can also produce an MCP tool error.

Metadata is intentionally sparse: `attempts` appears when greater than one,
`retries` when greater than zero, and cache/proxy/rendering flags when true.
`include_headers=true` adds response headers to scrape metadata. Selector results
include `css_selector_applied` and `elements_matched`; Markdown and text can include
`page_metadata`. Optional fields may differ by provider.

### Link response

`scrape_extract_links` uses the same batch totals and per-item success/error fields.
A successful item's `data` contains `links` and `count`:

```json
{
  "links": [
    {"url": "https://example.com/about", "text": "About", "title": ""}
  ],
  "count": 1
}
```

Relative URLs resolve against the scraped page. Links retain their scheme, so
clients should validate schemes before navigation. The link response model does
not expose scrape metadata, even though its tool accepts `include_headers`.

### Examples

These are arguments to MCP `tools/call`, not REST endpoints:

```json
{"name": "scrape_url", "arguments": {"urls": ["https://example.com/article"], "css_selector": "article", "strip_tags": ["script", "style"]}}
```

```json
{"name": "scrape_url_html", "arguments": {"urls": ["https://example.com/"], "css_selector": "meta[property^='og:']"}}
```

```json
{"name": "scrape_url_text", "arguments": {"urls": ["https://example.com/app"], "render_js": true, "css_selector": "#main-content"}}
```

```json
{"name": "scrape_extract_links", "arguments": {"urls": ["https://example.com/", "https://example.org/"], "css_selector": "nav a"}}
```

Selectors use BeautifulSoup/Soup Sieve: tags, `.class`, `#id`, attribute selectors,
descendants, comma-separated alternatives, and supported pseudo-classes. Filtering
keeps matched elements before tag stripping and conversion; no matches produce
empty content or links.

### Retries and TLS

The requests provider verifies certificates by default. It retries timeouts,
connection failures, and transient HTTP statuses `408`, `425`, `429`, `500`, `502`,
`503`, and `504`. The default three retries wait 1, 2, then 4 seconds, in addition
to network time. Permanent HTTP errors such as `404` return without retries.
Playwright has its own browser retry behavior.

## Perplexity and OpenRouter

`perplexity` and `perplexity_reason` register at startup only when a usable backend
is configured. Direct Perplexity needs its optional SDK and `PERPLEXITY_API_KEY`;
OpenRouter uses `OPENROUTER_API_KEY`. `PERPLEXITY_PROVIDER` selects `auto`,
`perplexity`, or `openrouter`; `auto` prefers a usable direct Perplexity backend.
Restart after adding the first backend so the tools register.

| Tool | Required parameter | Optional parameters |
|------|--------------------|---------------------|
| `perplexity` | `messages: list[dict[str, str]]`, with `role` and `content` | `model="sonar"`, `temperature=null`, `max_tokens=null` |
| `perplexity_reason` | `query: str` | `temperature=null`, `max_tokens=null` |

Null temperature/token values use service environment defaults: `0.3` and `4000`
unless configured otherwise. The reasoning model defaults to `sonar-reasoning-pro`
and can be configured with `PERPLEXITY_REASONING_MODEL`.

Only `sonar` is enabled initially. Opt into other supported models with
`PERPLEXITY_ENABLED_MODELS` or `perplexity_enabled_models` in runtime config.
The model set is `sonar`, `sonar-pro`, `sonar-reasoning`, `sonar-reasoning-pro`, and
`sonar-deep-research`. Disabled models fail before making a paid request. The
reasoning tool therefore requires an enabled reasoning model.

Responses contain `content`, `model`, `citations`, `usage`, and `metadata`.
Usage contains available token counts. Inspect `metadata.error` for service
failures. See [Configuration](CONFIGURATION.md) for backend and model settings.

## Administrative HTTP routes

| Route | Purpose |
|-------|---------|
| `GET /healthz` | Public container health check |
| `GET /` | Authenticated dashboard |
| `GET /api/stats` | Authenticated metrics and cache statistics |
| `GET /api/config` | Runtime values, defaults, and supported model/provider information |
| `POST /api/config` | Apply a JSON body shaped `{"config": {"verify_ssl": true}}` |
| `POST /api/cache/clear` | Clear the current JSON cache and reset counters |
| `GET /api/requests/{request_id}/details` | Request details and available cached content |

Use `Authorization: Bearer <token>` or HTTP Basic username `admin` with the token
as password. Without a configured token, administrative routes return `503`;
missing/incorrect credentials return `401`. Mutation requests require
`Content-Type: application/json`. Config bodies are limited to 64 KiB. Browser
origins are checked, and authenticated responses use `Cache-Control: no-store`.

API keys and proxy URLs are masked in returned config. Omit unchanged secrets or
send their mask back to preserve them; an empty string clears the runtime value.
Updates are in memory and reset on restart. See [Configuration](CONFIGURATION.md)
for environment fallbacks and settings that are only descriptive at runtime.

## Optional MCP capabilities

Resources and prompts are disabled by default. Enable them with
`--enable-resources` / `--enable-prompts`, or `ENABLE_RESOURCES=true` /
`ENABLE_PROMPTS=true`. There are no `--disable-*` CLI flags.

Resources include `cache://stats`, `cache://requests`,
`cache://request/{request_id}` and its `/content` and `/metadata` variants;
`config://current`, `config://defaults`, `config://scraping`, `config://cache`,
`config://perplexity`; and `server://info`, `server://metrics`, `server://tools`.
They expose server-wide information to trusted MCP clients.

Prompts include webpage analysis, summarization, extraction, page comparison,
SEO/link/metadata/accessibility audits, topic research, fact checking, competitive
analysis, and news roundups. Use `prompts/list` for exact names and argument schemas;
`prompts/get` returns a workflow template, not executed research.

`ENABLE_CACHE_TOOLS=true` additionally registers `cache_stats`,
`cache_clear_expired`, and `cache_clear_all`. These tools are accessible through MCP
and do not inherit HTTP admin-token authentication. Enable them only for clients
allowed to inspect or clear the shared cache.
