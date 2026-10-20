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
- [ ] Resolve the dependency graph against current advisories, raise security floors,
      and document any advisory that cannot be eliminated.
- [ ] Prevent proxy credential disclosure and unsafe configuration round-trips,
      enable TLS verification by default, and enforce an explicit admin access boundary.
- [ ] Eliminate unsafe pickle deserialization from persistent cache reads without
      deleting existing cache data.
- [ ] Restore inexpensive mandatory lint, format, type, test, build, and dependency
      audit checks; configure routine dependency maintenance and release validation.
- [ ] Enable available GitHub security protections and protect `main` with the
      validated checks. Record any API permission or platform limitation.
- [ ] Review the SearXNG proposal against release scope and either implement a
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
