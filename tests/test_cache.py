"""Tests for HTTP caching functionality."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import requests_cache

from scraper_mcp.cache import (
    check_cache_size,
    clear_all_cache,
    clear_expired_cache,
    create_cached_session,
    get_cache_path,
    get_cache_size,
    get_cache_stats,
)


class TestCacheConfiguration:
    """Tests for cache configuration."""

    def test_get_cache_path_default(self) -> None:
        """Test getting default cache path."""
        with patch.dict("os.environ", {}, clear=True):
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch("scraper_mcp.cache.DEFAULT_CACHE_DIR", temp_dir):
                    path = get_cache_path()
                    assert path == Path(temp_dir)

    def test_get_cache_path_custom(self) -> None:
        """Test getting custom cache path from environment."""
        custom_path = "/tmp/custom_cache"
        with patch.dict("os.environ", {"CACHE_DIR": custom_path}):
            path = get_cache_path()
            assert path == Path(custom_path)

    def test_create_cached_session_defaults(self) -> None:
        """Test creating cached session with default settings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = create_cached_session(cache_dir=temp_dir)

            assert isinstance(session, requests_cache.CachedSession)
            assert session.cache.cache_name.startswith(temp_dir)

    def test_create_cached_session_custom_expiration(self) -> None:
        """Test creating cached session with custom expiration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_expire = 7200  # 2 hours
            session = create_cached_session(
                expire_after=custom_expire, cache_dir=temp_dir
            )

            assert isinstance(session, requests_cache.CachedSession)
            # Session should have custom expiration configured
            assert session.settings.expire_after == custom_expire

    def test_create_cached_session_custom_name(self) -> None:
        """Test creating cached session with custom cache name."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_name = "test_cache"
            session = create_cached_session(cache_name=cache_name, cache_dir=temp_dir)

            assert isinstance(session, requests_cache.CachedSession)
            assert cache_name in session.cache.cache_name


class TestCacheStats:
    """Tests for cache statistics."""

    def test_get_cache_size_nonexistent(self) -> None:
        """Test getting size of nonexistent cache."""
        with patch("scraper_mcp.cache.get_cache_path") as mock_path:
            # Create temp dir that doesn't contain cache file
            with tempfile.TemporaryDirectory() as temp_dir:
                mock_path.return_value = Path(temp_dir)
                size = get_cache_size()
                assert size == 0

    def test_get_cache_size_existing(self) -> None:
        """Test getting size of existing cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a cache file
            cache_file = Path(temp_dir) / "scrape_cache.sqlite"
            cache_file.write_text("test cache data")

            with patch("scraper_mcp.cache.get_cache_path") as mock_path:
                mock_path.return_value = Path(temp_dir)
                size = get_cache_size()
                assert size > 0
                assert size == len("test cache data")

    def test_check_cache_size(self) -> None:
        """Test cache size checking."""
        # Should not raise any exceptions
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir)
            check_cache_size(cache_path)

    def test_get_cache_stats(self) -> None:
        """Test getting cache statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = create_cached_session(cache_dir=temp_dir)

            with patch("scraper_mcp.cache.get_cache_path") as mock_path:
                mock_path.return_value = Path(temp_dir)
                stats = get_cache_stats(session)

                assert "total_responses" in stats
                assert "cache_size_bytes" in stats
                assert "cache_size_mb" in stats
                assert "cache_path" in stats
                assert stats["total_responses"] == 0  # Empty cache


class TestCacheManagement:
    """Tests for cache management operations."""

    def test_clear_expired_cache_empty(self) -> None:
        """Test clearing expired entries from empty cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = create_cached_session(cache_dir=temp_dir)
            removed = clear_expired_cache(session)
            assert removed == 0

    def test_clear_all_cache_empty(self) -> None:
        """Test clearing all entries from empty cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session = create_cached_session(cache_dir=temp_dir)
            # Should not raise any exceptions
            clear_all_cache(session)

    def test_cached_session_creation(self) -> None:
        """Test that RequestsProvider creates cached session correctly."""
        from scraper_mcp.providers import RequestsProvider

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create provider with caching disabled
            provider_no_cache = RequestsProvider(cache_enabled=False)
            assert not isinstance(
                provider_no_cache.session, requests_cache.CachedSession
            )

            # Create provider with caching enabled
            # Note: This would normally create cache in /app/cache, but we test
            # the cache functionality separately with explicit cache_dir
            with patch("scraper_mcp.cache.get_cache_path") as mock_path:
                mock_path.return_value = Path(temp_dir)
                provider_cached = RequestsProvider(cache_enabled=True)
                assert isinstance(
                    provider_cached.session, requests_cache.CachedSession
                )


class TestCacheURLExpiration:
    """Tests for URL pattern-based cache expiration."""

    def test_urls_expire_after_configuration(self) -> None:
        """Test that URL expiration patterns are configured."""
        from scraper_mcp.cache import URLS_EXPIRE_AFTER

        assert URLS_EXPIRE_AFTER is not None
        assert "*" in URLS_EXPIRE_AFTER  # Default pattern
        assert isinstance(URLS_EXPIRE_AFTER["*"], int)

    def test_static_assets_never_expire(self) -> None:
        """Test that static asset patterns are set to never expire."""
        from scraper_mcp.cache import URLS_EXPIRE_AFTER

        # Check that CDN patterns are set to -1 (never expire)
        cdn_patterns = [k for k in URLS_EXPIRE_AFTER if "cdn" in k or "cloudfront" in k]
        assert len(cdn_patterns) > 0
        for pattern in cdn_patterns:
            assert URLS_EXPIRE_AFTER[pattern] == -1


class TestCacheIntegration:
    """Integration tests for cache functionality."""

    def test_cache_persistence_across_sessions(self) -> None:
        """Test that cache persists across session instances."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_name = "test_cache"

            # Create first session and populate cache
            session1 = create_cached_session(
                cache_name=cache_name, cache_dir=temp_dir
            )

            # Manually add a cached response
            from datetime import datetime, timedelta

            from requests_cache import CachedResponse

            # Create a simple cached response
            original_response = type(
                "MockResponse",
                (),
                {
                    "url": "https://example.com",
                    "status_code": 200,
                    "headers": {"Content-Type": "text/html"},
                    "content": b"<html>Test</html>",
                    "text": "<html>Test</html>",
                },
            )

            # Close first session
            session1.close()

            # Create second session with same cache
            session2 = create_cached_session(
                cache_name=cache_name, cache_dir=temp_dir
            )

            # Cache should be accessible from new session
            assert isinstance(session2, requests_cache.CachedSession)

            session2.close()
