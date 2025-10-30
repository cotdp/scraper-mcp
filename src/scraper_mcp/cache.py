"""HTTP caching configuration using requests-cache."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import requests_cache
from requests_cache import CachedSession

# Configure logging
logger = logging.getLogger(__name__)

# Default cache settings
DEFAULT_CACHE_DIR = "/app/cache"
DEFAULT_CACHE_NAME = "scrape_cache"
DEFAULT_EXPIRE_AFTER = 3600  # 1 hour in seconds
CACHE_SIZE_WARNING_THRESHOLD = 900 * 1024 * 1024  # 900MB (90% of 1GB)

# URL pattern-based expiration rules
# Patterns are matched using glob-style wildcards
URLS_EXPIRE_AFTER = {
    "*.cdn.com/static/*": -1,  # Never expire static assets
    "*.cloudfront.net/*": -1,  # Never expire CDN assets
    "*api*/realtime/*": 300,  # 5 minutes for realtime API data
    "*api*/live/*": 300,  # 5 minutes for live data
    "*": DEFAULT_EXPIRE_AFTER,  # Default 1 hour for everything else
}


def get_cache_path() -> Path:
    """Get the cache file path.

    Returns environment variable CACHE_DIR if set, otherwise uses default.
    Falls back to a local .cache directory if the default path is not accessible.

    Returns:
        Path to the cache directory
    """
    cache_dir = os.getenv("CACHE_DIR", DEFAULT_CACHE_DIR)
    cache_path = Path(cache_dir)

    # Try to create cache directory
    try:
        cache_path.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        # Fallback to local .cache directory for development/testing
        cache_path = Path.cwd() / ".cache"
        cache_path.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"Could not create cache at {cache_dir}, using fallback: {cache_path}"
        )

    return cache_path


def get_cache_size() -> int:
    """Get the current size of the cache in bytes.

    Returns:
        Cache size in bytes, or 0 if cache doesn't exist
    """
    cache_path = get_cache_path()
    cache_file = cache_path / f"{DEFAULT_CACHE_NAME}.sqlite"

    if cache_file.exists():
        return cache_file.stat().st_size

    return 0


def check_cache_size(cache_path: Path | None = None) -> None:
    """Check cache size and log warning if it exceeds threshold.

    Args:
        cache_path: Optional specific cache path to check
    """
    if cache_path is None:
        cache_path = get_cache_path()

    cache_file = cache_path / f"{DEFAULT_CACHE_NAME}.sqlite"

    size = 0
    if cache_file.exists():
        size = cache_file.stat().st_size

    size_mb = size / (1024 * 1024)

    logger.info(f"Current cache size: {size_mb:.2f} MB")

    if size >= CACHE_SIZE_WARNING_THRESHOLD:
        logger.warning(
            f"Cache size ({size_mb:.2f} MB) exceeds warning threshold "
            f"({CACHE_SIZE_WARNING_THRESHOLD / (1024 * 1024):.0f} MB). "
            "Consider clearing expired entries."
        )


def create_cached_session(
    expire_after: int = DEFAULT_EXPIRE_AFTER,
    cache_name: str | None = None,
    cache_dir: str | Path | None = None,
    backend: str = "sqlite",
) -> CachedSession:
    """Create a configured CachedSession for HTTP requests.

    Args:
        expire_after: Default cache expiration time in seconds (default: 3600)
        cache_name: Name for the cache file (default: scrape_cache)
        cache_dir: Directory to store cache (default: /app/cache)
        backend: Cache backend to use (default: sqlite)

    Returns:
        Configured CachedSession instance
    """
    # Resolve cache location
    if cache_dir is None:
        cache_dir = get_cache_path()
    else:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

    if cache_name is None:
        cache_name = DEFAULT_CACHE_NAME

    cache_path = cache_dir / cache_name

    logger.info(f"Initializing cache at: {cache_path}")

    # Create session with comprehensive caching configuration
    session = requests_cache.CachedSession(
        cache_name=str(cache_path),
        backend=backend,
        expire_after=expire_after,
        urls_expire_after=URLS_EXPIRE_AFTER,
        # Respect server Cache-Control headers
        cache_control=True,
        # Serve stale cache if requests fail
        stale_if_error=True,
        # Only cache successful responses (2xx status codes)
        allowable_codes=[200, 203, 300, 301, 308],
        # Ignore authorization headers and API keys in cache key
        ignored_parameters=["api_key", "access_token", "auth", "key", "token"],
        # Additional allowable HTTP methods for caching
        allowable_methods=["GET", "HEAD"],
        # Match headers for cache key (None = ignore headers)
        match_headers=False,
    )

    # Log cache configuration
    logger.info(
        f"Cache configured: expire_after={expire_after}s, "
        f"cache_control=True, stale_if_error=True"
    )

    # Check cache size on initialization
    check_cache_size(cache_dir)

    return session


def clear_expired_cache(session: CachedSession) -> int:
    """Remove expired entries from cache.

    Args:
        session: CachedSession instance

    Returns:
        Number of expired entries removed
    """
    logger.info("Clearing expired cache entries...")

    # Get count before
    responses_before = len(session.cache.responses)

    # Remove expired responses
    session.cache.delete(expired=True)

    # Get count after
    responses_after = len(session.cache.responses)
    removed = responses_before - responses_after

    logger.info(f"Removed {removed} expired entries from cache")

    return removed


def clear_all_cache(session: CachedSession) -> None:
    """Clear all cached entries.

    Args:
        session: CachedSession instance
    """
    logger.warning("Clearing all cache entries...")

    # Get count before
    responses_before = len(session.cache.responses)

    # Clear all cache
    session.cache.clear()

    logger.info(f"Cleared {responses_before} total entries from cache")


def get_cache_stats(session: CachedSession) -> dict[str, int | float]:
    """Get cache statistics.

    Args:
        session: CachedSession instance

    Returns:
        Dictionary with cache statistics
    """
    total_responses = len(session.cache.responses)
    cache_size = get_cache_size()
    cache_size_mb = cache_size / (1024 * 1024)

    return {
        "total_responses": total_responses,
        "cache_size_bytes": cache_size,
        "cache_size_mb": round(cache_size_mb, 2),
        "cache_path": str(get_cache_path() / f"{DEFAULT_CACHE_NAME}.sqlite"),
    }
