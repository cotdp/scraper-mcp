# Repository Guide

This file describes the current Scraper MCP implementation and verification
workflow. Follow the session's AGENTS instructions for authorization, Git, and
handoff requirements. Preserve unrelated edits and never read or modify secrets.

## Project and commands

Scraper MCP is a Python 3.12+ application built with the MCP Python SDK's FastMCP
1.x API, Pydantic v2, requests, BeautifulSoup/lxml, and markdownify. Dependencies
are managed with uv; optional extras are `perplexity`, `playwright`, and `dev`.

```bash
uv sync --locked --all-extras
uv run --no-sync python -m scraper_mcp
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy src/ scripts/
bun install --frozen-lockfile
bun run check
uv build --no-sources
```

Run tests with the credential/proxy isolation shown in [docs/TESTING.md](docs/TESTING.md).
Focused pytest commands can append a file or `-k` filter and `--no-cov`. Do not
install arbitrary new package versions to repair a lock mismatch; update metadata
and the lock deliberately, then validate them together.

The CLI accepts positional `transport`, `host`, and `port`. Defaults are
`streamable-http`, `127.0.0.1`, and `8000`; the alternative transport is `sse`.
There is no stdio CLI option. Resources/prompts are opt-in through
`--enable-resources`, `--enable-prompts`, or their `ENABLE_*` environment settings.

## Code map

- `server.py`: FastMCP instance, transport-security defaults, tool/custom-route
  registration, and `run_server()`.
- `__main__.py`: CLI argument parsing. `__init__.py` derives `__version__` from
  installed package metadata, so install the project before importing it.
- `tools/router.py`: registered MCP tool signatures and delegation to services.
- `tools/service.py`: batch orchestration, semaphore limits, HTML transformations,
  sparse response metadata, and request metrics.
- `models/`: Pydantic response models and supported Perplexity models/providers.
- `core/providers.py`: default requests provider and lazy Playwright selection.
- `providers/requests_provider.py`: requests-backed fetches, retries, caching,
  proxy handling, TLS verification, and credential redaction.
- `providers/playwright_provider.py`: Chromium/browser-context pooling and
  JavaScript rendering. Browser packages are optional outside the Docker image.
- `services/perplexity_service.py`: direct Perplexity SDK and OpenRouter HTTP
  backends, model allowlisting, and normalized responses/errors.
- `utils.py`: BeautifulSoup/Soup Sieve selection, markdown/text conversion, link
  resolution, and page metadata extraction.
- `cache_manager.py`: public cache API, TTL policy, key generation, and statistics.
- `cache_storage.py`: transactional SQLite storage with strict versioned JSON.
- `admin/security.py`: token authentication and browser request protections.
- `admin/router.py`, `admin/service.py`: administrative HTTP handlers and volatile
  runtime configuration. Do not assume every reported setting changes behavior;
  check its consumers before changing or documenting it.
- `dashboard/`: authenticated HTML dashboard and template assets.
- `resources/`, `prompts/`: optional MCP read resources and prompt templates.
- `scripts/check_release.py`, `scripts/smoke_image.py`: publication guard and
  offline production-container verification.

## Tool contracts

All scraping tools accept `urls: list[str]` and return a batch envelope, including
for one URL. `scrape_url` returns Markdown, `scrape_url_html` raw HTML,
`scrape_url_text` plain text, and `scrape_extract_links` link objects. Do not add
examples using a singular `url` argument or a `scrape_url_markdown` tool.

`BatchScrapeResponse` contains `total`, `successful`, `failed`, and `results`.
Each result contains the requested `url`, `success`, and either a `data` response
or an `error`. Link batches use the analogous model. A successful MCP call can
still contain failed URL results. The tool layer limits batch concurrency to eight.

Selector filtering runs before tag stripping and conversion. Requests retries
transient failures with exponential delays; details and exact tool arguments are
in [docs/API.md](docs/API.md). Use the generated MCP schemas as the contract when
changing tools, and keep tests/models/docs aligned.

Perplexity tools register at startup when a usable configured backend exists.
`auto` prefers direct Perplexity with its SDK/key, otherwise OpenRouter. Only
`sonar` is enabled initially; other models require explicit opt-in. Tests must not
make paid requests or inherit local keys.

## Security and persistence

The CLI binds to loopback, and Compose publishes a loopback host port. Containers
listen on `0.0.0.0:8000` internally. MCP DNS-rebinding protection is enabled; this
is not client authentication. Restrict MCP to trusted clients or an authenticated
gateway, as it can fetch network resources and use configured paid providers.

Dashboard and `/api/*` routes require `SCRAPER_ADMIN_TOKEN`, even from loopback.
Without it, they return HTTP 503. Bearer auth and HTTP Basic (`admin`, token) are
supported; `/healthz` remains public. Admin mutations require JSON and enforce
browser-origin checks. Returned proxy URLs/API keys are masked; preserve masks
on roundtrip and avoid leaking credentials through responses or logs. TLS
certificate verification defaults to enabled.

The cache writes `cache-v1.sqlite3` and supports TTL, LRU, statistics, and
thread/process concurrency. Serialization admits JSON primitives and the explicit
`ScrapeResult` schema only. Never load pickle, import arbitrary encoded types, or
migrate legacy diskcache contents. Existing legacy files remain untouched. Cache
size metrics count encoded keys/values, excluding SQLite overhead. Tests use
temporary cache directories, not persisted deployment data.

## Testing and shipping

Tests use pytest, pytest-asyncio, pytest-mock, and provider/network mocks. Add
focused regressions for meaningful behavioral or security boundaries. The cache
suite includes hostile records and thread/process concurrency; admin tests cover
both HTTP transports; release-guard tests use disposable Git histories.

The quality workflow performs locked dependency installation, Ruff, mypy, pytest,
strict dependency auditing, Bun/Biome checks, and wheel/sdist builds. CodeQL scans
Python separately. PR/main CI does not build Docker images. Run the documented
local offline image smoke before release preparation is considered validated.

Follow [RELEASE.md](RELEASE.md): one reviewed PR, owner merge, matching package and
lock versions, then a new tag on merged code. The publication workflow repeats
quality checks and image smoke before pushing amd64/arm64 images to Docker Hub
and GHCR. Manual publication is restricted to `main`; unmerged commits and
mismatched tags fail the release guard. Never delete/reuse tags or move deployment
aliases to perform rollback; deploy the recorded previous immutable digest.
