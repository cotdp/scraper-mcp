# Security policy

Report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/cotdp/scraper-mcp/security/advisories/new).
Do not include credentials or private scraped content in public issues.

## Deployment boundary

The MCP endpoint is intended for trusted clients. Scraping can reach addresses
accessible from the server, including private services, and optional AI tools
can incur provider charges. The admin token does not authenticate MCP clients.
Keep MCP on loopback or a trusted private network. Remote deployments must add
an authenticated gateway and appropriate egress controls.

The command-line server binds to `127.0.0.1` by default. Docker listens on
`0.0.0.0` inside its container; the supplied Compose files publish only to host
loopback. Do not expose the port publicly without an authenticated gateway.

## Administration

Set `SCRAPER_ADMIN_TOKEN` through your deployment's secret injection mechanism.
The dashboard and all `/api/*` routes require it, including loopback requests.
Without a token, administration is disabled with HTTP 503; `/healthz` stays public.
Loopback alone cannot authorize administration because an MCP scraper can itself
make requests to localhost.

API clients send `Authorization: Bearer <token>`. Browsers use HTTP Basic sign-in
with username `admin` and the token as the password. Use HTTPS for remote access.
The token is never included in configuration responses, URLs, or browser storage.
Rotate it by replacing the injected value and restarting the service.

Mutations require `application/json`. Browser requests must have the exact same
origin. An HTTPS reverse proxy can explicitly allow its public origin through
comma-separated `SCRAPER_ADMIN_ALLOWED_ORIGINS`, for example
`https://scraper.example.com`. Wildcards are unsupported. Forwarding headers do
not grant access or add trusted origins.

Proxy URLs are returned as `[REDACTED]`. Omitting a value or returning its existing
mask preserves it; an empty string clears it. Treat configuration updates as
privileged operations. TLS certificate verification is enabled by default;
prefer configuring trusted CA certificates over disabling verification.

## Persistent data

The cache uses SQLite and a closed JSON format. It never imports Python objects
from cache records or reads legacy DiskCache pickle files. New storage is
`cache-v1.sqlite3`; upgrades start cold and leave old files untouched.

Limit filesystem access to the service account. Old cache files and historical
logs can still contain data written by older versions. Upgrading does not erase
those bytes or rotate previously exposed credentials.

## Verification

Required CI includes locked dependency auditing, tests, type checks, lint,
formatting, and package builds. CodeQL analyzes Python code. Dependency updates
are grouped and scheduled; security updates and secret push protection are enabled.
Release publication validates that the commit is merged into `main` and that
the tag matches the project version before registry credentials are used.
