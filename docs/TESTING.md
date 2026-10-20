# Testing Guide

Use Python 3.12+ and the committed uv lockfile. Install every optional provider for
local verification, then use the same commands as CI:

```bash
uv sync --locked --all-extras
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy src/ scripts/
bun install --frozen-lockfile
bun run check
```

## Isolated test suite

Tests mock external providers and use temporary caches. To avoid inheriting local
credentials, proxy settings, or dotenv files during imports, run in a subshell:

```bash
(
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
  export NO_PROXY='*' no_proxy='*' PYTHON_DOTENV_DISABLED=1
  export PERPLEXITY_API_KEY='' OPENROUTER_API_KEY='' SCRAPEOPS_API_KEY=''
  export SCRAPER_ADMIN_TOKEN='' SCRAPER_ADMIN_ALLOWED_ORIGINS=''
  export CACHE_DIR="$(mktemp -d)"
  uv run --no-sync pytest --cov-report=term-missing --cov-report=xml
)
```

The test output is the source of truth for counts and coverage. `pyproject.toml`
enables strict markers, automatic asyncio support, and coverage reports. To focus
on one area, replace the pytest command above with, for example:

```bash
uv run --no-sync pytest tests/test_admin_security.py --no-cov
uv run --no-sync pytest tests/test_cache_security.py --no-cov
uv run --no-sync pytest tests/test_release_guard.py --no-cov
```

Useful test boundaries include:

- `test_utils.py`: HTML conversion, links, selectors, and metadata.
- `test_providers.py`, `test_server.py`: provider errors and batch tool results.
- `test_admin_security.py`, `test_admin_config.py`, `test_tls_defaults.py`: auth,
  request validation, credential preservation, and certificate verification.
- `test_proxy_credentials.py`: credential redaction and cache exposure.
- `test_cache_security.py`: JSON-only decoding, legacy-cache isolation, TTL/LRU,
  storage permissions, and concurrent threads/processes.
- `test_release_guard.py`: release decisions against disposable Git histories.

Add tests at the boundary where behavior changes. Mock network providers for
ordinary tests; keep paid provider calls and browser binaries out of unit tests.
Do not use the production cache for test fixtures.

## Dependency audit and distribution build

```bash
uv export --locked --all-extras --no-emit-project --output-file /tmp/scraper-mcp-audit.txt
uv run --no-sync pip-audit --strict --disable-pip --require-hashes --progress-spinner off --requirement /tmp/scraper-mcp-audit.txt
uv build --no-sources
```

The audit covers the exported locked graph, including optional and development
dependencies, for the current environment. A clean audit does not replace testing
the wheel's dependency metadata or the container's system/browser components.
The build writes a wheel and sdist under `dist/`; it does not publish them.

## Production-image smoke

```bash
docker build -t scraper-mcp:release-check .
docker run --rm --network none -i scraper-mcp:release-check python - < scripts/smoke_image.py
```

The smoke runs as the image's non-root user and starts its server on container
loopback. It checks health, admin authentication, TLS defaults, a packaged
dashboard, OpenRouter-only tool registration, real MCP HTTP calls, static scraping,
Chromium rendering, and cache writes using synthetic local content. It does not
mount a production volume or contact paid providers. The release workflow runs
this smoke on amd64 before publishing the multi-architecture image.

## Manual MCP integration

Start the HTTP server in one terminal:

```bash
uv run --no-sync python -m scraper_mcp streamable-http 127.0.0.1 8000
```

Run this client against it using the project's MCP 1.x SDK. The CLI supports
Streamable HTTP and SSE; launching it through `stdio_client` will not work.

```python
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main() -> None:
    async with streamable_http_client("http://127.0.0.1:8000/mcp") as (
        read_stream,
        write_stream,
        get_session_id,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print([tool.name for tool in (await session.list_tools()).tools])
            result = await session.call_tool(
                "scrape_url",
                arguments={"urls": ["https://example.com/"], "max_retries": 0},
            )
            if result.isError:
                raise RuntimeError(result.content)
            payload = result.structuredContent
            if payload is None:
                raise RuntimeError("Expected a structured batch response")
            if payload["failed"]:
                raise RuntimeError(payload["results"])
            print(payload["results"][0]["data"]["content"])


asyncio.run(main())
```

This example makes a real public HTTP request. Use the offline container smoke for
repeatable checks without network access. MCP's optional session-ID callback is
intentionally unused because the server runs in stateless mode. The v1 client
transport yields three values; examples targeting MCP v2 may use different APIs.

For Perplexity/OpenRouter live checks, use an already approved injected credential
and explicitly chosen enabled model. Record which provider/model succeeded;
synthetic tool registration alone does not verify live upstream access.

## Continuous integration

[CI](../.github/workflows/ci.yml) runs for PRs into `main`, pushes to `main`, and
release-workflow calls. It performs locked installation, Ruff, mypy, isolated
pytest, dependency auditing, dashboard asset checks, and distribution builds.
Wheel/sdist artifacts are retained for 14 days. There is no automatic PyPI upload.
[CodeQL](../.github/workflows/codeql.yml) runs separately for Python on PRs, main,
a weekly schedule, and manual dispatch.

Docker publication runs only for guarded version tags or manual dispatch on
`main`. PR CI does not build or publish images. Follow [Release](../RELEASE.md)
for the owner-merge and publication sequence.
