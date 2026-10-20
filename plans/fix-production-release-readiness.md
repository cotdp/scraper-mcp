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
- [ ] Prevent proxy credential disclosure and unsafe configuration round-trips,
      enable TLS verification by default, and enforce an explicit admin access boundary.
- [x] Eliminate unsafe pickle deserialization from persistent cache reads without
      deleting existing cache data.
- [ ] Restore inexpensive mandatory lint, format, type, test, build, and dependency
      audit checks; configure routine dependency maintenance and release validation.
- [ ] Enable available GitHub security protections and protect `main` with the
      validated checks. Record any API permission or platform limitation.
- [x] Review the SearXNG proposal against release scope and either implement a
      bounded integration or record a concrete follow-up.
- [ ] Prepare the next version, migration notes, release notes, and safe publish procedure.
- [ ] Run full local validation, production-container smoke tests, and an independent
      review; resolve findings and verify hosted CI on the final commit.
- [ ] Ship one clean, pushed PR and a session summary with remaining owner actions.

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
