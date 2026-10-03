# RequestsProvider credential attribution — phase 1

Branch: `fix/quota-wave2-20261004-scraper`
Base: verified `origin/main` at `9d3e9ba`; unrelated open PRs #3 and #4.
Cutoff: 2026-10-05 12:18:22 Asia/Singapore.

## Acceptance criteria

- ScrapeOps results and relative links retain the requested target attribution.
- Configured proxy credentials do not reach provider/MCP results, new cache entries,
  cache hits, request metrics, application logs, or formatted request exceptions.
- Direct request redirects and existing retry behavior remain supported.
- Regression fixtures use synthetic credentials, mocked HTTP, and temporary caches.
- No auth/SSRF redesign, secret files, live proxy calls, deployment, or unrelated PR edits.

## Work

- [x] Read repository/lane instructions, verify base and open PRs, and trace boundaries.
- [x] Reproduce output/cache/error/log leaks with focused synthetic regression tests.
- [x] Apply the smallest boundary fix and verify the regressions and existing checks.
- [ ] Commit, push, create/link one PR, and record validation limitations.

## Evidence

`RequestsProvider.scrape` copies proxy URLs into `proxy_config`, uses `response.url`
for ScrapeOps attribution, and rethrows request exceptions containing transport URLs.
`clean_metadata` forwards `proxy_config`; all four tool wrappers persist exception
strings in metrics. Link extraction uses the provider result URL as its base.
`admin.service` also logs raw proxy environment URLs at import.

Legacy cached results can contain these fields after the fix; unsafe entries must be
treated as misses and replaced by safe results without migrating the cache database.

The original 32 credential regression cases all failed against the unchanged base.
The final matrix also covers proxy-only failures, exception attachments/chaining,
FastMCP serialization, cache resources, request details, and content-type casing.
Review caught an overbroad cache filter; a failing homepage regression established
that filtering must require the ScrapeOps `api_key` transport query, not just its host.

## Validation and limitations

- Python 3.12.6, frozen dependency installation; only mock HTTP and temporary caches.
- `uv run pytest tests -q --tb=short`: 195 passed, including 53 credential regressions.
- `uv run ruff check src tests`, `uv run ruff format --check src tests`,
  `npm run check`, `uv build`, and `git diff --check` pass.
- `uv run mypy src --no-incremental` reports the same 23 pre-existing errors as an
  untouched archive of main; the repository already makes this CI step nonblocking.
- Unsafe legacy cache values are hidden on reads and replaced on a successful fetch.
  Previously stored bytes/logs are not purged; no live cache or configuration is changed.
- Separate finding: `_public_config` still returns raw configured proxy URLs to the
  administration/configuration surfaces (including opt-in `config://current`). That
  configuration editing/round-trip flow is outside this RequestsProvider attribution
  phase and remains unchanged. Third-party wire-debug logs are not exercised by mock HTTP.
