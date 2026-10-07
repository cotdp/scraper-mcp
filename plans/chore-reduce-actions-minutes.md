# Reduce GitHub Actions minutes

Branch: `chore/reduce-actions-minutes`

## Cost drivers

- The latest 100 runs include 26 CI main pushes and 23 Docker main builds, plus two PR runs of each. CI spawned three jobs and Docker built two architectures for two registries.

## Acceptance criteria

- [x] PRs run one fast Ruff check with concurrency cancellation and a five minute limit.
- [x] Full tests, type checks, and web lint move to local quality gates before push.
- [x] Multi architecture publishing runs on version tags or a manual main branch dispatch, retaining the `latest` image tag in both registries.
- [x] Validate workflows with actionlint and run the PR command locally.

Local gate: `uvx ruff check src tests && uv run --all-extras pytest tests -q`; run `npm run check` for web changes.

Validation for this change: actionlint passed; Ruff passed; 142 tests passed locally.
