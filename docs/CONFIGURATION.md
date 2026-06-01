# Configuration Guide

Complete configuration reference for Scraper MCP.

## Environment Variables

### Server Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `TRANSPORT` | streamable-http | Transport type: `streamable-http` or `sse` |
| `HOST` | 0.0.0.0 | Host to bind to |
| `PORT` | 8000 | Port to bind to |
| `CACHE_DIR` | /app/cache | Cache directory path |
| `ENABLE_CACHE_TOOLS` | false | Expose cache management tools |
| `DISABLE_RESOURCES` | false | Disable MCP resources |
| `DISABLE_PROMPTS` | false | Disable MCP prompts |

### Feature Flags

Resources and prompts are enabled by default. To reduce context overhead for LLM clients:

```bash
# Via environment variables
DISABLE_RESOURCES=true
DISABLE_PROMPTS=true

# Via CLI flags
python -m scraper_mcp --disable-resources
python -m scraper_mcp --disable-prompts
python -m scraper_mcp --disable-resources --disable-prompts
```

### Perplexity AI

| Variable | Default | Description |
|----------|---------|-------------|
| `PERPLEXITY_API_KEY` | - | API key (enables AI tools when set). Overridable at runtime. |
| `PERPLEXITY_ENABLED_MODELS` | `sonar` | Comma-separated allowlist of usable models (opt-in). |
| `PERPLEXITY_MODEL` | sonar | Default model for the `perplexity` tool |
| `PERPLEXITY_REASONING_MODEL` | sonar-reasoning-pro | Model used by the `perplexity_reason` tool |
| `PERPLEXITY_TEMPERATURE` | 0.3 | Default temperature |
| `PERPLEXITY_MAX_TOKENS` | 4000 | Default max tokens |

Get your API key from [Perplexity AI](https://www.perplexity.ai/).

#### Model allowlist (opt-in)

To control cost, only `sonar` is enabled by default. The more expensive models —
`sonar-pro`, `sonar-reasoning`, `sonar-reasoning-pro`, and `sonar-deep-research` —
must be explicitly enabled. Requesting a disabled model returns an error **without**
making a (billable) API call.

> ⚠️ Because `sonar-reasoning-pro` is disabled by default, the `perplexity_reason`
> tool returns a "model not enabled" error until you opt that model in.

Enable models at startup via the environment:

```bash
PERPLEXITY_ENABLED_MODELS=sonar,sonar-pro,sonar-reasoning-pro
```

…or override the API key and enabled models at runtime via the admin API (changes
are not persisted and reset on restart):

```bash
# Toggle which models are enabled
curl -X POST http://localhost:8000/api/config \
  -H 'Content-Type: application/json' \
  -d '{"config": {"perplexity_enabled_models": ["sonar", "sonar-pro"]}}'

# Override the API key (the GET endpoint returns it masked, e.g. "pplx...7890")
curl -X POST http://localhost:8000/api/config \
  -H 'Content-Type: application/json' \
  -d '{"config": {"perplexity_api_key": "pplx-..."}}'
```

Unknown model names are rejected. Available models are advertised under
`available_perplexity_models` in `GET /api/config`.

---

## Proxy Configuration

The scraper supports HTTP/HTTPS proxies through standard environment variables.

### Basic Setup

Create a `.env` file:

```bash
# HTTP proxy
HTTP_PROXY=http://proxy.example.com:8080
http_proxy=http://proxy.example.com:8080

# HTTPS proxy
HTTPS_PROXY=http://proxy.example.com:8080
https_proxy=http://proxy.example.com:8080

# Bypass proxy for specific hosts
NO_PROXY=localhost,127.0.0.1,.local
no_proxy=localhost,127.0.0.1,.local
```

### With Docker Compose

Docker Compose automatically reads `.env` files:

```bash
docker-compose up -d
```

### With Docker Run

```bash
docker run -p 8000:8000 \
  -e HTTP_PROXY=http://proxy.example.com:8080 \
  -e HTTPS_PROXY=http://proxy.example.com:8080 \
  -e NO_PROXY=localhost,127.0.0.1,.local \
  cotdp/scraper-mcp:latest
```

### Proxy with Authentication

```bash
HTTP_PROXY=http://username:password@proxy.example.com:8080
HTTPS_PROXY=http://username:password@proxy.example.com:8080
```

### Build-Time vs Runtime

Proxy configuration works at two stages:

1. **Build time**: Package installation (apt, uv, pip)
2. **Runtime**: HTTP requests from the scraper

Both uppercase and lowercase variable names are supported.

---

## ScrapeOps Proxy Integration

[ScrapeOps](https://scrapeops.io/) is a premium proxy service for bypassing anti-bot measures, rendering JavaScript, and geo-targeting.

### Features

- JavaScript rendering for SPAs
- Residential proxies (less likely to be blocked)
- Geo-targeting by country
- Automatic header rotation
- High success rate with smart retries

### Quick Setup

Add your API key to `.env`:

```bash
SCRAPEOPS_API_KEY=your_api_key_here
```

All requests automatically route through ScrapeOps when enabled.

### Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRAPEOPS_API_KEY` | - | API key (required to enable) |
| `SCRAPEOPS_RENDER_JS` | false | Enable JavaScript rendering |
| `SCRAPEOPS_RESIDENTIAL` | false | Use residential proxies |
| `SCRAPEOPS_COUNTRY` | - | Target country (us, gb, de, etc.) |
| `SCRAPEOPS_KEEP_HEADERS` | false | Keep original headers |
| `SCRAPEOPS_DEVICE` | desktop | Device type: desktop, mobile, tablet |

### Full Example

```bash
# .env file
SCRAPEOPS_API_KEY=your_api_key_here
SCRAPEOPS_RENDER_JS=true
SCRAPEOPS_RESIDENTIAL=true
SCRAPEOPS_COUNTRY=us
SCRAPEOPS_DEVICE=desktop
```

---

## Runtime Configuration

The dashboard Config tab allows runtime adjustments without restart.

### Available Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Concurrency | 8 | Max parallel requests (1-50) |
| Default Timeout | 30 | Request timeout in seconds |
| Max Retries | 3 | Retry attempts on failure |
| Cache TTL - Default | 3600 | Default cache duration (1 hour) |
| Cache TTL - Realtime | 300 | API/live data cache (5 minutes) |
| Cache TTL - Static | 86400 | Static content cache (24 hours) |

### Important Notes

- Changes apply immediately without restart
- Settings reset when the server restarts
- Use `.env` file for permanent configuration

---

## DNS Rebinding Protection

MCP 1.24+ enables DNS rebinding protection by default.

### Default Allowed Hosts

```
127.0.0.1:*
localhost:*
[::1]:*
```

### Adding Custom Hosts

For external access (e.g., OrbStack, reverse proxy):

```bash
# In .env file
FASTMCP_ALLOWED_HOSTS=["127.0.0.1:*","localhost:*","[::1]:*","your-domain.local","your-domain.local:*"]
FASTMCP_ALLOWED_ORIGINS=["http://127.0.0.1:*","http://localhost:*","http://[::1]:*","https://your-domain.local"]
```

### Disabling Protection

Not recommended for production:

```bash
FASTMCP_TRANSPORT_SECURITY__ENABLE_DNS_REBINDING_PROTECTION=false
```
