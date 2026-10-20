# Production release readiness

Branch: `fix/production-release-readiness`
Base: `be6e8e39d07b67e8be3b4986ee3fbfd4aa323b38`

## Scope and constraints

Prepare the next production release through one PR. Fix the known dependency,
credential, transport, cache, CI, and release-process gaps before considering new
features. Never merge automatically, push to `main`, publish an unmerged release,
read or modify `.env*` or `secrets/**`, or alter the existing deployment.

The original checkout remains intact at
`/home/mcutler/workspaces/carrotly/scraper-mcp`. Its historical work is preserved
in recovery commit `0a464b2` and largely integrated through PR #4. Both untracked
files match `origin/main` exactly. A clean worktree avoids reintroducing older
code over subsequent credential fixes.

## Acceptance criteria and execution

- [x] Start a clean branch from current remote `main` and record custody of local work.
- [x] Resolve the dependency graph against current advisories, raise security floors,
      and document any advisory that cannot be eliminated.
- [x] Prevent proxy credential disclosure and unsafe configuration round-trips,
      enable TLS verification by default, and enforce an explicit admin access boundary.
- [x] Eliminate unsafe pickle deserialization from persistent cache reads without
      deleting existing cache data.
- [x] Restore inexpensive mandatory lint, format, type, test, build, and dependency
      audit checks; configure routine dependency maintenance and release validation.
- [x] Enable available GitHub security protections and protect `main` with the
      validated checks. Record any API permission or platform limitation.
- [x] Review the SearXNG proposal against release scope and either implement a
      bounded integration or record a concrete follow-up.
- [x] Prepare the next version, migration notes, release notes, and safe publish procedure.
- [x] Run full local validation, production-container smoke tests, and an independent
      review; resolve findings and verify hosted CI on the final commit.
- [x] Ship one clean, pushed PR and a session summary with remaining owner actions.
- [?] Clear production publication (blocked: 25 unique critical/high upstream OS
      advisories have no available fixes in the scanned Debian packages; owner
      security review and merge remain required).
- [?] Verify live OpenRouter account behavior (blocked: no injected OpenRouter key).

## Decisions and evidence

- GitHub currently reports 35 open Dependabot alerts across 13 packages. Advisory
  reachability and registry availability must be checked rather than assuming all
  findings are exploitable or all suggested versions are installable.
- The current source already explicitly enables MCP DNS-rebinding protection and
  stateless HTTP. Retain those protections through dependency upgrades.
- Keep expensive multi-architecture image publication restricted to release tags
  or a manual dispatch from merged `main`.
- Production publication follows owner merge. This session validates artifacts
  without updating deployed services or the production `latest` image.
- The upgraded graph retains MCP 1.x (`>=1.30,<2`) and enforces advisory minimums.
  The hashed all-extras export passes `pip-audit` with no known vulnerabilities
  and no vulnerability exclusions.
- Replace DiskCache with SQLite and strict JSON in `cache-v1.sqlite3`. Old files
  are never read or deleted. Eviction limits and size metrics measure encoded
  keys and values, excluding SQLite page, index, and WAL overhead.
- Baseline: 224 tests passed. After upgrades, 92 provider/tool/HTML tests passed;
  cache/resource and credential-boundary suites passed independently. Full
  integrated validation follows the remaining changes.
- Defer SearXNG to a separate feature release: it adds an independently deployed
  search service and is not required to remediate or validate this release.
  Follow-up acceptance criteria: optional internal-only Compose profile, bounded
  typed `search` results, timeouts and unavailable-sidecar behavior, query cache
  policy, configuration documentation, and a live search-to-scrape smoke test.
  The design remains in `docs/research/searxng-integration.md`.
- Require admin authentication even on loopback: MCP scraping can otherwise
  reach a local administration route. Browser Basic authentication and API
  Bearer authentication share the injected token. No token means disabled
  administration; MCP remains a trusted-client interface.
- Independent review caught two additional release gaps: TLS policy was missing
  from HTTP cache keys, and uv-only constraints did not protect wheel consumers.
  A reproduced TLS-cache regression now passes; patched floors are included in
  distribution metadata.
- Local integrated validation: 387 tests passed with 79% coverage; Ruff,
  strict mypy (41 source/script files), Biome, actionlint, package builds, and the
  hashed all-extras dependency audit passed. No advisory exclusions were used.
- Browser checks passed authenticated administration, masked configuration
  round-trips, and TLS defaults. A reproduced navigation overflow at 390px is
  fixed. A bounded live Perplexity Sonar request passed (8 total tokens).
  Live OpenRouter verification remains unavailable without an injected key.
- GitHub now has secret scanning, push protection, private vulnerability
  reporting, and automated security updates enabled. Main requires a PR,
  conversation resolution, and current `quality` / `Analyze (python)` checks from
  GitHub Actions, including for administrators; force pushes and deletion are
  disabled. Zero approving reviews permits the solo owner to merge.
- Container scanning found outdated bootstrap tools outside the Python lockfile.
  Update uv to 0.13.3 (patched rustls) and OS packages; remove unused bootstrap
  pip and gcc/libxml2/libxslt development packages. The rebuilt image passes the
  complete offline smoke. Trivy reports no Python, Node-runtime, or uv findings
  and no available OS fixes; remaining OS counts are 1 critical, 67 high,
  146 medium, 145 low, and 5 unknown package/advisory pairs.
- The critical OS finding is CVE-2026-6653 in libxml2 pulled in by the graphics
  stack through libllvm19. Application lxml uses bundled libxml2 2.14.6, but
  graphics-path reachability remains unconfirmed. Do not treat the application
  audit as clearing the image. Full evidence and follow-up steps are in
  `docs/releases/0.5.0-validation.md`.
- Hosted `quality`, `Analyze (python)`, and CodeQL checks passed at implementation
  commit `0d6c5a2`. The final documentation handoff also runs these checks; the PR
  records the current result. PR: https://github.com/cotdp/scraper-mcp/pull/6.
