# Integrate recovered local work

Branch: `feat/preserve-local-work-20261003` (PR #4)

## Background

PR #4 began on 2026-10-03 as a byte-exact recovery checkpoint of uncommitted work in two
local checkouts, both at base `9d3e9ba`. The snapshot commit is `0a464b2`; its
`recovery/2026-10-03/manifest.json` records every path, mode and SHA-256. On 2026-10-08 the
snapshots still matched the live maintenance checkout byte for byte, and none of the work had
reached `main` (`main` gained only #5, the proxy credential boundary, and #3, the reduced CI).

## Acceptance criteria

- [x] Verify snapshot blobs against the manifest hashes and against the live checkout.
- [x] Merge current `main` into the branch rather than rewriting history.
- [x] Apply the recovered source, test, docs, Dockerfile and lock changes as real code, with
  conflicts resolved in favour of #5's credential boundary.
- [x] Drop the CI hunk (the mypy job it edited was removed by #3).
- [x] Cover the conflict point: a proxied permanent HTTP error stops after one attempt and
  still raises the sanitized exception.
- [x] Local gate: `uv lock --check`, Ruff check and format, mypy, full pytest suite and a
  production image build with an in-container health check.
- [x] Remove the snapshot dumps from the final tree; custody remains in commit `0a464b2`.
- [x] Close the OpenRouter credential leak found in review (2026-10-08): transport and
  unexpected errors report the exception type only; upstream error text is redacted of API
  keys and environment proxy credentials before it is returned or recorded in metrics.
  `tests/test_perplexity_credentials.py` fails on `f53d364` and passes after the fix.
- [ ] Owner applies the `.env.example` hunk (blocked: agent policy forbids writing `.env*`
  files). Source: `recovery/2026-10-03/blob-c2dc0a44….snapshot` at `0a464b2`; it documents
  `OPENROUTER_API_KEY` and `PERPLEXITY_PROVIDER`, which README and `docs/CONFIGURATION.md`
  already cover.

## Not integrated, by design

- `~/workspaces/github/scraper-mcp/docker-compose.yml`, which binds the port to loopback and
  this host's tailnet address. That is host-specific deployment state for the live service,
  so it stays uncommitted in that checkout (snapshot `recovery/2026-10-03/1-scraper-mcp/` at
  `0a464b2`).
- `stash@{0}` in the same checkout, which bumps the version in `uv.lock` to 0.4.0. `main`
  already has that change.

## Recovery

To restore any original byte, check out `0a464b2` and copy the snapshot named in its manifest.
The original checkouts were not modified.
