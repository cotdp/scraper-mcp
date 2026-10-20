"""Authentication and browser protections for the administrative HTTP surface."""

from __future__ import annotations

import base64
import binascii
import hmac
import os
from collections.abc import Awaitable, Callable
from functools import wraps
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

AdminHandler = Callable[[Request], Awaitable[Response]]


def _origin(value: str) -> tuple[str, str, int] | None:
    """Parse an exact HTTP origin; never accept credentials, paths, or wildcards."""
    try:
        if any(character.isspace() for character in value) or "\\" in value:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or "*" in parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return None
        return (
            parsed.scheme,
            parsed.hostname,
            parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


def _token_matches(authorization: str, token: str) -> bool:
    parts = authorization.split(" ")
    if len(parts) != 2:
        return False
    scheme, credential = parts
    if scheme.lower() == "basic":
        try:
            decoded = base64.b64decode(credential, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return False
        username, separator, credential = decoded.partition(":")
        if username != "admin" or not separator:
            return False
    elif scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(credential.encode("utf-8"), token.encode("utf-8"))


def _error(message: str, status_code: int) -> JSONResponse:
    response = JSONResponse({"status": "error", "message": message}, status_code=status_code)
    if status_code == 401:
        response.headers["WWW-Authenticate"] = 'Basic realm="Scraper MCP admin", charset="UTF-8"'
    return response


def authorize_admin(request: Request) -> Response | None:
    """Require a configured token, including for loopback requests.

    The scraper itself can request loopback URLs, so a local peer is not proof
    of admin authority. Forwarding headers never grant access either.
    """
    for header in ("host", "origin", "authorization"):
        if len(request.headers.getlist(header)) > 1:
            return _error("Ambiguous request headers", 400)

    host = request.headers.get("host", "")
    request_origin = _origin(f"{request.scope['scheme']}://{host}")
    if request_origin is None:
        return _error("Invalid request host", 400)

    token = os.getenv("SCRAPER_ADMIN_TOKEN", "")
    if not token:
        return _error(
            "Admin routes are disabled. Configure SCRAPER_ADMIN_TOKEN, then use Bearer "
            "authentication or sign in as admin with the token as password.",
            503,
        )
    if not _token_matches(request.headers.get("authorization", ""), token):
        return _error("Admin authentication required", 401)

    # Basic credentials may be sent automatically by a browser. Check the exact
    # origin (including the port) before exposing data or accepting a mutation.
    origin_header = request.headers.get("origin")
    if origin_header is not None:
        allowed_origins = {request_origin}
        for value in os.getenv("SCRAPER_ADMIN_ALLOWED_ORIGINS", "").split(","):
            configured_origin = _origin(value.strip())
            if configured_origin is not None:
                allowed_origins.add(configured_origin)
        origin = _origin(origin_header)
        if origin is None or origin not in allowed_origins:
            return _error("Cross-origin admin requests are forbidden", 403)
    if request.headers.get("sec-fetch-site") == "cross-site":
        return _error("Cross-site admin requests are forbidden", 403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            return _error("Admin mutations require application/json", 415)
    return None


def require_admin(handler: AdminHandler) -> AdminHandler:
    """Protect a route and keep responses out of shared/browser caches."""

    @wraps(handler)
    async def protected(request: Request) -> Response:
        denied = authorize_admin(request)
        response = denied if denied is not None else await handler(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    return protected
