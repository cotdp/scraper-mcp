# Development Guide

Use Python 3.12+, uv, and Bun. Docker is needed for production-image verification.
Keep work on a task branch, preserve unrelated edits, and submit changes through
one PR. See [CLAUDE.md](../CLAUDE.md) for the current code map.

## Local setup

```bash
git clone https://github.com/cotdp/scraper-mcp.git
cd scraper-mcp
uv sync --locked --all-extras
bun install --frozen-lockfile
uv run --no-sync python -m scraper_mcp
```

The default server uses Streamable HTTP on `127.0.0.1:8000`, with MCP at `/mcp`.
Use a different local port if needed:

```bash
uv run --no-sync python -m scraper_mcp streamable-http 127.0.0.1 3100
```

The CLI also supports `sse`; it does not support stdio. Resources and prompts are
opt-in with `--enable-resources` / `--enable-prompts` or their `ENABLE_*` settings.

Inject `SCRAPER_ADMIN_TOKEN` through your approved local environment if you need
the dashboard or admin API. Browser sign-in uses `admin` and that token as the
password. Without it, administrative routes return 503 while `/healthz` and MCP
remain available. The admin token does not authenticate MCP, so keep the listener
private. See [Configuration](CONFIGURATION.md) and [Security](../SECURITY.md).

## Verification

```bash
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy src/ scripts/
bun run check
uv build --no-sources
```

Use the isolated test command in [Testing](TESTING.md) to prevent inherited
credentials, proxies, or persistent caches from influencing tests. That guide also
covers focused pytest runs, dependency auditing, a real MCP client example, and
the offline production-image smoke. Use `uv run --no-sync ruff check . --fix` and
`uv run --no-sync ruff format .` when intentionally applying Python fixes.

Dependencies come from `pyproject.toml` and `uv.lock`. When changing a dependency,
update the manifest deliberately, regenerate the lock with `uv lock`, and repeat
relevant checks and the dependency audit. Dashboard tooling uses `package.json`
and `bun.lock`; avoid mixing package managers.

## Architecture and extension points

The requests provider handles ordinary HTTP/HTTPS scraping. `render_js=true`
selects the implemented Playwright provider, which manages Chromium and bounded
browser contexts. Selection lives in `core/providers.py`; the shared interface is
`ScraperProvider.scrape()` / `supports_url()` in `providers/base.py`.

MCP tool signatures live in `tools/router.py`; service functions perform batching
and transformations. Every scraping call uses `urls: list[str]`, and every result
is a batch envelope with individual successes/failures. `scrape_url` produces
Markdown, `scrape_url_html` HTML, `scrape_url_text` text, and
`scrape_extract_links` links. See [API](API.md) for parameter and response details.

BeautifulSoup/lxml and Soup Sieve perform HTML parsing and selector filtering.
Selected elements are kept before optional tag stripping and markdown/text
conversion. Metadata normalization and request metrics live in the tool services.

The separate Perplexity service supports direct SDK requests and OpenRouter HTTP
requests. Tools register only when a usable backend is configured at startup.
Model allowlisting controls which paid models may be invoked.

Caching uses `CacheManager` over strict JSON in a new SQLite database. Preserve
its schema validation, transactional expiry/eviction, and explicit `ScrapeResult`
encoding. Do not introduce pickle or migrate legacy cache contents. The admin
security decorator protects custom HTTP routes; MCP resources/cache tools have a
separate trusted-client boundary.

When adding a tool or provider:

1. Add typed service/provider behavior within the existing module structure.
2. Define or extend Pydantic response models and the registered tool signature.
3. Validate inputs at the boundary and avoid propagating credentials in errors.
4. Add focused provider/service tests with synthetic responses and temporary
   storage; update the API docs and discovery information.
5. Run the relevant checks and review the complete diff before shipping the PR.

Python formatting uses a 100-character line limit, Ruff import sorting, and strict
mypy. Keep implementation details in the owning module rather than expanding
`server.py` into a business-logic layer.

## Docker development

```bash
docker build -t scraper-mcp:custom .
docker run --rm --network none -i scraper-mcp:custom python - < scripts/smoke_image.py
```

For an interactive local server using an already injected admin token:

```bash
docker run --rm -p 127.0.0.1:8000:8000 -e SCRAPER_ADMIN_TOKEN scraper-mcp:custom
```

The Dockerfile uses a Python 3.12 slim runtime image, copies a pinned uv binary,
installs locked production extras and Chromium, then runs as a non-root user.
It binds to `0.0.0.0:8000` inside the container; the host port should remain
loopback unless an explicit access boundary is in place. Do not mount production
cache volumes for development or image smoke tests.

The supplied Compose files also publish to loopback. Check their configuration
and injected environment before starting them. `docker compose build` and
`docker compose up -d` are available for an intentionally configured local stack.

## CI and release

Quality CI runs for PRs into `main`, main pushes, and release-workflow calls. It
checks Python formatting/lint/types/tests, audits the locked dependency graph,
checks dashboard assets, and builds wheel/sdist artifacts. CodeQL scans Python
separately. PR CI does not build or publish Docker images.

The release workflow publishes amd64/arm64 images only after version/ancestry
guards, quality checks, and the offline image smoke. It is triggered by stable
version tags or manual dispatch on `main`. Follow [Release](../RELEASE.md): owner
merge first, tag only merged code, and deploy verified immutable image digests.
