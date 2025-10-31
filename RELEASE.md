# Release Guide

This document describes the release process for Scraper MCP, including semantic versioning strategy, Docker image publishing, and automation workflows.

## Semantic Versioning

We follow [Semantic Versioning 2.0.0](https://semver.org/) with the format `MAJOR.MINOR.PATCH`:

- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality additions
- **PATCH** version for backwards-compatible bug fixes

### Version Examples

```
v1.0.0 - Initial stable release
v1.1.0 - Add new MCP tool
v1.1.1 - Fix bug in existing tool
v2.0.0 - Breaking change to tool API
```

## Release Workflow

### Prerequisites

Before creating a release, ensure:

1. ✅ All tests pass (`pytest`)
2. ✅ Code is linted and formatted (`ruff check`, `ruff format`)
3. ✅ Type checking passes (`mypy src/`)
4. ✅ Changes are committed to `main` branch
5. ✅ Docker Hub secrets are configured in GitHub repository

### Docker Hub Secrets Setup

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

1. **DOCKERHUB_USERNAME**: Your Docker Hub username (e.g., `cotdp`)
2. **DOCKERHUB_TOKEN**: Docker Hub Personal Access Token
   - Generate at https://hub.docker.com/settings/security
   - Create "New Access Token" with Read & Write permissions
   - Copy the token immediately (it won't be shown again)

**Note**: GHCR authentication is automatic via `GITHUB_TOKEN` (no setup needed).

### Creating a Release

1. **Determine the version bump**

   Based on your changes:
   - Breaking changes → MAJOR bump (1.0.0 → 2.0.0)
   - New features → MINOR bump (1.0.0 → 1.1.0)
   - Bug fixes → PATCH bump (1.0.0 → 1.0.1)

2. **Create and push git tag**

   ```bash
   # Ensure you're on main and up to date
   git checkout main
   git pull origin main

   # Create annotated tag with release notes
   git tag -a v1.0.0 -m "Release v1.0.0

   - Feature: Add CSS selector filtering
   - Feature: Multi-platform Docker images
   - Fix: Improve error handling
   "

   # Push tag to trigger CI/CD
   git push origin v1.0.0
   ```

3. **Monitor GitHub Actions**

   The workflow automatically:
   - Builds Docker images for linux/amd64 and linux/arm64
   - Tags with multiple variants (1.0.0, 1.0, 1, latest)
   - Pushes to Docker Hub and GHCR simultaneously
   - Generates build attestations for supply chain security
   - Creates summary with pull commands

   Monitor progress at: https://github.com/cotdp/scraper-mcp/actions/workflows/docker-publish.yml

4. **Verify publication**

   Once the workflow completes, verify images are available:

   ```bash
   # Docker Hub
   docker pull cotdp/scraper-mcp:1.0.0
   docker inspect cotdp/scraper-mcp:1.0.0

   # GitHub Container Registry
   docker pull ghcr.io/cotdp/scraper-mcp:1.0.0
   docker inspect ghcr.io/cotdp/scraper-mcp:1.0.0

   # Verify multi-platform support
   docker manifest inspect cotdp/scraper-mcp:1.0.0
   # Should show: linux/amd64, linux/arm64
   ```

5. **Create GitHub Release** (optional)

   Create a formal GitHub release with release notes:
   - Go to https://github.com/cotdp/scraper-mcp/releases/new
   - Select the tag you just pushed
   - Auto-generate release notes or write custom ones
   - Publish release

## Docker Image Tags

For each version release (e.g., `v1.2.3`), the following tags are created:

| Tag | Description | Example |
|-----|-------------|---------|
| `latest` | Latest stable release | `cotdp/scraper-mcp:latest` |
| `{version}` | Full semantic version | `cotdp/scraper-mcp:1.2.3` |
| `{major}.{minor}` | Minor version | `cotdp/scraper-mcp:1.2` |
| `{major}` | Major version | `cotdp/scraper-mcp:1` |
| `main-{sha}` | Main branch commits | `cotdp/scraper-mcp:main-abc1234` |

All tags are available on **both** Docker Hub and GitHub Container Registry:
- Docker Hub: `docker.io/cotdp/scraper-mcp:<tag>`
- GHCR: `ghcr.io/cotdp/scraper-mcp:<tag>`

## Automated Builds

### On Tag Push (Release)

Trigger: Pushing a tag matching `v*.*.*` (e.g., `v1.0.0`)

Behavior:
- Builds multi-platform images (linux/amd64, linux/arm64)
- Creates semantic version tags (1.0.0, 1.0, 1)
- Updates `latest` tag
- Publishes to Docker Hub **and** GHCR
- Generates provenance attestation

### On Main Branch Push (Development)

Trigger: Pushing commits to `main` branch

Behavior:
- Builds multi-platform images
- Creates `main-{sha}` tag for testing
- Does **not** update `latest` tag
- Publishes to both registries

### On Pull Request (Testing)

Trigger: Creating/updating a pull request

Behavior:
- Builds images to verify Dockerfile works
- Does **not** push images to registries
- Runs as CI check only

## Rollback Procedure

If a release has issues, you can rollback by pointing `latest` to a previous version:

```bash
# Pull the last known good version
docker pull cotdp/scraper-mcp:1.0.0

# Tag it as latest locally
docker tag cotdp/scraper-mcp:1.0.0 cotdp/scraper-mcp:latest

# Push to override latest (requires Docker Hub credentials)
docker login
docker push cotdp/scraper-mcp:latest
```

**Note**: For GHCR, use `docker login ghcr.io` with a GitHub Personal Access Token.

Alternatively, create a new patch release with the fix (recommended).

## Version History

### v0.1.0 (Initial Release)
- Initial MCP server implementation
- Four scraping tools: raw HTML, markdown, text, link extraction
- Docker support with multi-platform builds
- GitHub Actions CI/CD
- Published to Docker Hub and GHCR

## Best Practices

### DO ✅

- Follow semantic versioning strictly
- Write descriptive git tag annotations
- Test releases in a staging environment first
- Create GitHub releases with changelog
- Increment versions sequentially (no skipping)

### DON'T ❌

- Delete published tags (creates confusion)
- Reuse version numbers (breaks caching)
- Push incomplete tags (test locally first)
- Use non-semver formats (e.g., `v1.0` without patch)
- Skip testing before releases

## Troubleshooting

### Workflow fails with "Login failed"

**Problem**: Docker Hub authentication failed

**Solution**:
1. Verify `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets are set correctly
2. Check token permissions (needs Read & Write)
3. Regenerate token if expired

### Images pushed but not visible

**Problem**: Images published but don't show in Docker Hub

**Solution**:
1. Wait 2-3 minutes for registry indexing
2. Check workflow logs for actual push confirmation
3. Verify repository exists at https://hub.docker.com/r/cotdp/scraper-mcp

### Multi-platform build fails

**Problem**: ARM64 build fails during workflow

**Solution**:
1. Check QEMU setup step succeeded
2. Verify Dockerfile has no platform-specific dependencies
3. Test locally with: `docker buildx build --platform linux/arm64 .`

### Tag created but workflow didn't run

**Problem**: Pushed tag but no workflow triggered

**Solution**:
1. Verify tag format matches `v*.*.*` pattern
2. Check workflow file is on `main` branch
3. Look for workflow in Actions tab (may be pending)

## Support

For issues with releases or CI/CD:
- Check workflow runs: https://github.com/cotdp/scraper-mcp/actions
- Open an issue: https://github.com/cotdp/scraper-mcp/issues
- Review workflow file: `.github/workflows/docker-publish.yml`
