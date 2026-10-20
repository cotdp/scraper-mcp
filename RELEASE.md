# Release Guide

Release preparation happens on one feature branch and PR. The owner reviews and
merges it; agents must not merge it, push to `main`, or tag unmerged work.
The next candidate is [0.5.0](docs/releases/0.5.0.md).

## Prepare and validate

1. Choose a new stable `MAJOR.MINOR.PATCH` version. For this pre-1.0 project,
   document incompatible behavior in the release notes and bump the minor version.
2. Keep `pyproject.toml`, `package.json`, and the root package in `uv.lock` aligned.
   Run `uv lock` after metadata changes. Python reports its installed distribution
   version; there is no separate source version constant to update.
3. Run the checks in [Testing](docs/TESTING.md), including the locked dependency
   audit, distribution build, and offline production-image smoke. Record any live
   provider checks that require credentials separately; synthetic checks do not
   establish that an external account or billing setup works.
4. Update `docs/releases/<version>.md`, review the complete diff, and wait for the
   PR's quality and CodeQL checks. Confirm the repository's dependency and secret
   alerts have been triaged. Do not bypass failed security checks.
5. Have the owner merge the PR. Publication must use the merged commit, including
   when GitHub creates a new commit through a squash or rebase merge.

The CI workflow builds wheel/sdist artifacts but does not upload them to PyPI.
There is no automated package-index submission workflow in this repository.

## Publish a merged release

Use a clean release checkout, preserving any other dirty working tree. After the
owner merges the preparation PR, fetch and check out the updated remote branch:

```bash
git fetch origin main --tags
git switch --detach origin/main
git status --short
```

Confirm that the checkout is clean, the intended release is in `origin/main`, and
its checks pass. For 0.5.0, run the same version and ancestry guard as publication:

```bash
GITHUB_EVENT_NAME=push GITHUB_REF=refs/tags/v0.5.0 \
  uv run --no-sync python scripts/check_release.py
```

The guard checks Python/dashboard/lockfile version agreement, the exact stable
version tag, and that `HEAD` is an ancestor of `origin/main`. It reports whether
this commit is the current tip, which controls moving image aliases. A manual
workflow dispatch is accepted only on `main`.

Only after these checks, the authorized release operator creates a new annotated
tag and pushes that tag:

```bash
git tag -a v0.5.0 -F docs/releases/0.5.0.md
git push origin refs/tags/v0.5.0
```

Never delete, move, force-push, or reuse a published tag or version. If a tagged
release needs code changes, prepare and merge a new version through another PR.

## What GitHub Actions publishes

[The image workflow](.github/workflows/docker-publish.yml) runs on `v*.*.*` tag
pushes or manual dispatch. It validates the release, calls the full quality
workflow, builds an amd64 image, and exercises it with
`scripts/smoke_image.py` using `--network none`. Only then does it publish
`linux/amd64` and `linux/arm64` images with provenance and SBOMs to:

- `docker.io/cotdp/scraper-mcp`
- `ghcr.io/cotdp/scraper-mcp`

Docker Hub requires the repository Actions secrets `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN`. GHCR uses the workflow's `GITHUB_TOKEN` with package-write
permission. Configure credentials through approved secret-management interfaces.

A version-tag run publishes the full version and `main-<sha>` image tags. If the
release commit is the current `origin/main` tip at validation, it also updates
`latest`, the major/minor alias, and the major alias. Historical release commits
cannot move those aliases backwards. A manual dispatch on current `main`
publishes the SHA tag and `latest`; it does not invent a Git version tag.

PRs and pushes to `main` run quality and CodeQL checks. They do not automatically
build or publish Docker images. The local image smoke is therefore an explicit
release-preparation check.

## Verify and deploy

Check the [publication run](https://github.com/cotdp/scraper-mcp/actions/workflows/docker-publish.yml)
for success in both registries. The summary records tags and the image digest.
Inspect both manifests, confirm both target architectures, and retain the digest:

```bash
docker buildx imagetools inspect cotdp/scraper-mcp:0.5.0
docker buildx imagetools inspect ghcr.io/cotdp/scraper-mcp:0.5.0
```

Deploy by the verified immutable digest, and record the previous deployed digest
and configuration before changing the deployment. Apply the migration notes in
[0.5.0](docs/releases/0.5.0.md), then check `/healthz`, authenticated administration,
and representative MCP requests in the target environment. Publish the prepared
GitHub release notes once publication and verification succeed.

## Rollback and failures

Rollback the deployment to its recorded prior image digest and compatible
configuration. Do not retag an older image as `latest`, alter Git tags, or reuse a
release version. The 0.5.0 cache uses a new database filename and leaves legacy
cache files intact; older images retain their older security behavior.

If publication fails, inspect the failed job before retrying. A failed login
requires correcting the relevant registry credential. A failed guard requires
correct version metadata or a merged commit, not skipping the guard. A successful
push to one registry does not prove the other succeeded; verify both before
announcing the release. Use a new patch release for any code correction.
