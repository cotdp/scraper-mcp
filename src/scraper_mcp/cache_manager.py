"""HTTP caching manager using diskcache."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import diskcache

# Configure logging
logger = logging.getLogger(__name__)

# Default cache settings
DEFAULT_CACHE_DIR = "/app/cache"
DEFAULT_SIZE_LIMIT = int(1e9)  # 1GB
CACHE_SIZE_WARNING_THRESHOLD = int(9e8)  # 900MB (90% of 1GB)

# Default TTL values in seconds
DEFAULT_TTL = 3600  # 1 hour
STATIC_ASSET_TTL = 86400  # 24 hours
REALTIME_DATA_TTL = 300  # 5 minutes


class CacheManager:
    """Thread-safe and process-safe cache manager using diskcache.

    Features:
    - Persistent disk-based caching with SQLite backend
    - Automatic size management with LRU eviction
    - TTL-based expiration per entry
    - Statistics tracking for monitoring
    - Process-safe for concurrent access
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        size_limit: int = DEFAULT_SIZE_LIMIT,
        eviction_policy: str = "least-recently-used",
        enable_statistics: bool = True,
    ) -> None:
        """Initialize the cache manager.

        Args:
            cache_dir: Directory for cache storage (default: /app/cache or .cache/)
            size_limit: Maximum cache size in bytes (default: 1GB)
            eviction_policy: Eviction policy when size limit reached (default: LRU)
            enable_statistics: Enable hit/miss statistics tracking
        """
        # Resolve cache directory
        if cache_dir is None:
            cache_dir = self._get_cache_directory()
        else:
            cache_dir = Path(cache_dir)

        self.cache_dir = cache_dir
        self.size_limit = size_limit

        # Initialize diskcache.Cache
        try:
            self.cache = diskcache.Cache(
                directory=str(cache_dir),
                size_limit=size_limit,
                eviction_policy=eviction_policy,
                statistics=enable_statistics,
                cull_limit=10,  # Remove up to 10 items when size limit reached
            )
            logger.info(
                f"Cache initialized at {cache_dir} with {size_limit / 1e9:.1f}GB limit"
            )
        except Exception as e:
            logger.error(f"Failed to initialize cache: {e}")
            raise

        # Check initial cache size
        self.check_size()

    def _get_cache_directory(self) -> Path:
        """Get cache directory path with fallback for development.

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

    def generate_cache_key(self, url: str, **kwargs: Any) -> str:
        """Generate a cache key from URL and optional parameters.

        Args:
            url: The URL being cached
            **kwargs: Additional parameters to include in cache key
                     (e.g., headers, method, body)

        Returns:
            Cache key string (hexdigest)
        """
        # Create a deterministic key from URL and parameters
        key_data = {
            "url": url,
            **kwargs,
        }
        # Sort keys for deterministic hashing
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get_ttl_for_url(self, url: str) -> int:
        """Determine appropriate TTL based on URL pattern.

        Args:
            url: URL to determine TTL for

        Returns:
            TTL in seconds
        """
        url_lower = url.lower()

        # Static assets and CDN content
        if any(pattern in url_lower for pattern in ['static', 'cdn', 'cloudfront']):
            return STATIC_ASSET_TTL

        # Real-time or API data
        if any(pattern in url_lower for pattern in ['api', 'realtime', 'live']):
            return REALTIME_DATA_TTL

        # Default TTL
        return DEFAULT_TTL

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache.

        Args:
            key: Cache key
            default: Default value if key not found

        Returns:
            Cached value or default
        """
        try:
            value = self.cache.get(key, default=default, retry=True)
            if value is not default:
                logger.debug(f"Cache HIT for key: {key[:16]}...")
            else:
                logger.debug(f"Cache MISS for key: {key[:16]}...")
            return value
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return default

    def set(
        self,
        key: str,
        value: Any,
        expire: int | None = None,
        retry: bool = True,
    ) -> bool:
        """Set value in cache with optional expiration.

        Args:
            key: Cache key
            value: Value to cache
            expire: Expiration time in seconds (None = no expiration)
            retry: Whether to retry on failure

        Returns:
            True if successful, False otherwise
        """
        try:
            return self.cache.set(key, value, expire=expire, retry=retry)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key existed and was deleted, False otherwise
        """
        try:
            return self.cache.delete(key, retry=True)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False

    def clear(self) -> None:
        """Clear all entries from cache and reset statistics."""
        try:
            self.cache.clear(retry=True)
            # Reset cache statistics (hits and misses)
            self.cache.stats(reset=True)
            logger.info("Cache cleared successfully and statistics reset")
        except Exception as e:
            logger.error(f"Cache clear error: {e}")

    def expire(self) -> int:
        """Remove expired entries from cache.

        Returns:
            Number of expired entries removed
        """
        try:
            count = self.cache.expire()
            logger.info(f"Removed {count} expired entries from cache")
            return count
        except Exception as e:
            logger.error(f"Cache expire error: {e}")
            return 0

    def get_stats(self) -> dict[str, int | float]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        stats = {}

        try:
            # Get cache volume (current size)
            volume = self.cache.volume()
            volume_mb = volume / (1024 * 1024)

            # Get statistics if enabled
            hits, misses = self.cache.stats(enable=True)
            hit_rate = hits / (hits + misses) if (hits + misses) > 0 else 0.0

            # Get entry count
            entry_count = len(self.cache)

            stats = {
                "entry_count": entry_count,
                "size_bytes": volume,
                "size_mb": round(volume_mb, 2),
                "size_limit_bytes": self.size_limit,
                "size_limit_mb": round(self.size_limit / (1024 * 1024), 2),
                "utilization_percent": round((volume / self.size_limit) * 100, 2),
                "hits": hits,
                "misses": misses,
                "hit_rate": round(hit_rate, 4),
                "cache_dir": str(self.cache_dir),
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            stats = {"error": str(e)}

        return stats

    def check_size(self) -> None:
        """Check cache size and log warning if approaching limit."""
        try:
            volume = self.cache.volume()
            volume_mb = volume / (1024 * 1024)

            logger.debug(f"Current cache size: {volume_mb:.2f} MB")

            if volume >= CACHE_SIZE_WARNING_THRESHOLD:
                logger.warning(
                    f"Cache size ({volume_mb:.2f} MB) exceeds warning threshold "
                    f"({CACHE_SIZE_WARNING_THRESHOLD / (1024 * 1024):.0f} MB). "
                    "Automatic eviction will occur on next write."
                )
        except Exception as e:
            logger.error(f"Error checking cache size: {e}")

    def close(self) -> None:
        """Close the cache and release resources."""
        try:
            self.cache.close()
            logger.info("Cache closed successfully")
        except Exception as e:
            logger.error(f"Error closing cache: {e}")

    def __enter__(self) -> CacheManager:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - close cache."""
        self.close()


# Global cache manager instance
_cache_manager: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """Get or create the global cache manager instance.

    Returns:
        Global CacheManager instance
    """
    global _cache_manager

    if _cache_manager is None:
        _cache_manager = CacheManager()

    return _cache_manager
