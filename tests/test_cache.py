"""Tests for HTTP caching functionality using diskcache."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from scraper_mcp.cache import clear_all_cache, clear_expired_cache, get_cache_stats
from scraper_mcp.cache_manager import CacheManager
from scraper_mcp.providers import RequestsProvider


class TestCacheManager:
    """Tests for CacheManager class."""

    def test_cache_manager_initialization(self) -> None:
        """Test cache manager initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=temp_dir)

            assert cache_manager.cache_dir == Path(temp_dir)
            assert cache_manager.size_limit == int(1e9)  # 1GB
            assert cache_manager.cache is not None

            cache_manager.close()

    def test_cache_key_generation(self) -> None:
        """Test cache key generation is deterministic."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=temp_dir)

            key1 = cache_manager.generate_cache_key("https://example.com")
            key2 = cache_manager.generate_cache_key("https://example.com")

            # Same URL should generate same key
            assert key1 == key2

            # Different URL should generate different key
            key3 = cache_manager.generate_cache_key("https://example.org")
            assert key1 != key3

            cache_manager.close()

    def test_cache_set_and_get(self) -> None:
        """Test setting and getting values from cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=temp_dir)

            key = "test_key"
            value = {"url": "https://example.com", "content": "test"}

            # Set value
            success = cache_manager.set(key, value)
            assert success is True

            # Get value
            cached_value = cache_manager.get(key)
            assert cached_value == value

            cache_manager.close()

    def test_cache_expiration(self) -> None:
        """Test cache expiration functionality."""
        import time

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=temp_dir)

            key = "test_key"
            value = "test_value"

            # Set value with 1 second expiration
            cache_manager.set(key, value, expire=1)

            # Should be in cache immediately
            assert cache_manager.get(key) == value

            # Wait for expiration
            time.sleep(1.1)

            # Should be expired
            assert cache_manager.get(key) is None

            cache_manager.close()

    def test_cache_delete(self) -> None:
        """Test deleting values from cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=temp_dir)

            key = "test_key"
            value = "test_value"

            # Set and verify
            cache_manager.set(key, value)
            assert cache_manager.get(key) == value

            # Delete and verify
            deleted = cache_manager.delete(key)
            assert deleted is True
            assert cache_manager.get(key) is None

            cache_manager.close()

    def test_cache_clear(self) -> None:
        """Test clearing all cache entries."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=temp_dir)

            # Add multiple entries
            for i in range(5):
                cache_manager.set(f"key_{i}", f"value_{i}")

            # Verify entries exist
            assert cache_manager.get("key_0") == "value_0"
            assert cache_manager.get("key_4") == "value_4"

            # Clear cache
            cache_manager.clear()

            # Verify all entries are gone
            for i in range(5):
                assert cache_manager.get(f"key_{i}") is None

            cache_manager.close()

    def test_get_ttl_for_url(self) -> None:
        """Test TTL determination based on URL patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=temp_dir)

            # Static assets - 24 hours
            assert cache_manager.get_ttl_for_url("https://cdn.example.com/style.css") == 86400
            assert cache_manager.get_ttl_for_url("https://static.example.com/logo.png") == 86400

            # Real-time data - 5 minutes
            assert cache_manager.get_ttl_for_url("https://api.example.com/realtime") == 300
            assert cache_manager.get_ttl_for_url("https://example.com/api/live") == 300

            # Default - 1 hour
            assert cache_manager.get_ttl_for_url("https://example.com/page") == 3600

            cache_manager.close()

    def test_cache_stats(self) -> None:
        """Test getting cache statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=temp_dir)

            # Add some entries
            for i in range(5):
                cache_manager.set(f"key_{i}", f"value_{i}" * 100)

            # Get some entries to register hits
            cache_manager.get("key_0")
            cache_manager.get("key_1")

            # Get cache miss
            cache_manager.get("nonexistent")

            stats = cache_manager.get_stats()

            assert "size_bytes" in stats
            assert "size_mb" in stats
            assert "hits" in stats
            assert "misses" in stats
            assert "hit_rate" in stats
            assert "cache_dir" in stats

            assert stats["hits"] >= 2
            assert stats["misses"] >= 1

            cache_manager.close()


class TestCacheManagerIntegration:
    """Integration tests for cache manager with providers."""

    @pytest.mark.asyncio
    async def test_requests_provider_with_cache(self) -> None:
        """Test RequestsProvider with caching enabled."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("scraper_mcp.cache_manager.DEFAULT_CACHE_DIR", temp_dir):
                # Create provider with caching
                provider = RequestsProvider(cache_enabled=True)

                assert provider.cache_enabled is True
                assert provider.cache_manager is not None

                provider.session.close()

    def test_requests_provider_without_cache(self) -> None:
        """Test RequestsProvider with caching disabled."""
        provider = RequestsProvider(cache_enabled=False)

        assert provider.cache_enabled is False
        assert provider.cache_manager is None

        provider.session.close()


class TestCacheUtilityFunctions:
    """Tests for cache utility functions."""

    def test_get_cache_stats(self) -> None:
        """Test get_cache_stats utility function."""
        stats = get_cache_stats()

        assert isinstance(stats, dict)
        assert "size_bytes" in stats or "error" in stats

    def test_clear_expired_cache(self) -> None:
        """Test clear_expired_cache utility function."""
        removed = clear_expired_cache()

        assert isinstance(removed, int)
        assert removed >= 0

    def test_clear_all_cache(self) -> None:
        """Test clear_all_cache utility function."""
        # Should not raise any exceptions
        clear_all_cache()


class TestCacheContextManager:
    """Tests for cache context manager functionality."""

    def test_context_manager(self) -> None:
        """Test cache manager as context manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with CacheManager(cache_dir=temp_dir) as cache_manager:
                cache_manager.set("test_key", "test_value")
                assert cache_manager.get("test_key") == "test_value"

            # Cache should be closed after exiting context
            # New cache manager can access persisted data
            with CacheManager(cache_dir=temp_dir) as cache_manager2:
                # Data should persist
                assert cache_manager2.get("test_key") == "test_value"


class TestCachePersistence:
    """Tests for cache persistence across manager instances."""

    def test_cache_persists_across_instances(self) -> None:
        """Test that cache persists when creating new manager instances."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # First manager instance
            cache_manager1 = CacheManager(cache_dir=temp_dir)
            cache_manager1.set("persistent_key", "persistent_value")
            cache_manager1.close()

            # Second manager instance with same directory
            cache_manager2 = CacheManager(cache_dir=temp_dir)
            value = cache_manager2.get("persistent_key")
            cache_manager2.close()

            # Value should persist
            assert value == "persistent_value"


class TestCacheSizeManagement:
    """Tests for automatic cache size management."""

    def test_cache_size_tracking(self) -> None:
        """Test cache size tracking."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_manager = CacheManager(cache_dir=temp_dir, size_limit=int(1e6))  # 1MB

            # Add some data
            large_data = "x" * 10000
            for i in range(10):
                cache_manager.set(f"key_{i}", large_data)

            stats = cache_manager.get_stats()

            assert stats["size_bytes"] > 0
            assert stats["size_mb"] > 0

            cache_manager.close()
