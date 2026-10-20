"""HTTP caching utilities using the SQLite/JSON cache manager."""

from __future__ import annotations

from scraper_mcp.cache_manager import CacheManager, get_cache_manager

__all__ = [
    "CacheManager",
    "clear_all_cache",
    "clear_expired_cache",
    "get_cache_manager",
    "get_cache_stats",
]


def get_cache_stats() -> dict[str, int | float | str]:
    """Get HTTP cache statistics.

    Returns:
        Dictionary with cache statistics
    """
    cache_manager = get_cache_manager()
    return cache_manager.get_stats()


def clear_expired_cache() -> int:
    """Remove expired entries from HTTP cache.

    Returns:
        Number of expired entries removed
    """
    cache_manager = get_cache_manager()
    return cache_manager.expire()


def clear_all_cache() -> None:
    """Clear all entries from HTTP cache."""
    cache_manager = get_cache_manager()
    cache_manager.clear()
