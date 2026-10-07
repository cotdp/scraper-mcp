"""Tests for scraper providers."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
import requests

from scraper_mcp.providers import RequestsProvider, ScrapeResult
from scraper_mcp.providers.playwright_provider import (
    BrowserPoolManager,
    PlaywrightProvider,
    get_browser_pool,
    is_playwright_available,
)


class TestRequestsProvider:
    """Tests for RequestsProvider."""

    @pytest.fixture
    def provider(self) -> RequestsProvider:
        """Create a RequestsProvider instance."""
        # Create provider with caching disabled for simpler testing
        return RequestsProvider(timeout=10, cache_enabled=False)

    def test_supports_http_urls(self, provider: RequestsProvider) -> None:
        """Test that provider supports HTTP URLs."""
        assert provider.supports_url("http://example.com")
        assert provider.supports_url("https://example.com")
        assert provider.supports_url("https://example.com/path?query=1")

    def test_rejects_non_http_urls(self, provider: RequestsProvider) -> None:
        """Test that provider rejects non-HTTP URLs."""
        assert not provider.supports_url("ftp://example.com")
        assert not provider.supports_url("file:///path/to/file")
        assert not provider.supports_url("javascript:alert('test')")
        assert not provider.supports_url("data:text/html,<h1>Test</h1>")

    def test_rejects_invalid_urls(self, provider: RequestsProvider) -> None:
        """Test that provider rejects invalid URLs."""
        assert not provider.supports_url("not a url")
        assert not provider.supports_url("")
        assert not provider.supports_url("://invalid")

    @pytest.mark.asyncio
    async def test_scrape_success(self, provider: RequestsProvider, sample_html: str) -> None:
        """Test successful scraping."""
        # Mock the session.get call
        mock_response = Mock()
        mock_response.url = "https://example.com"
        mock_response.text = sample_html
        mock_response.status_code = 200
        mock_response.headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Server": "nginx",
        }
        mock_response.encoding = "utf-8"
        mock_response.elapsed.total_seconds.return_value = 0.123

        # Mock run_in_executor to execute synchronously
        async def mock_executor(executor, func):
            return func()

        with patch.object(provider.session, "get", return_value=mock_response) as mock_get:
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_executor
                result = await provider.scrape("https://example.com")

                # Verify session.get was called correctly
                mock_get.assert_called_once()
                call_args = mock_get.call_args
                assert call_args[0][0] == "https://example.com"
                assert call_args[1]["timeout"] == 10
                assert "User-Agent" in call_args[1]["headers"]

                # Verify result
                assert isinstance(result, ScrapeResult)
                assert result.url == "https://example.com"
                assert result.content == sample_html
                assert result.status_code == 200
                assert result.content_type == "text/html; charset=utf-8"
                assert "elapsed_ms" in result.metadata

    @pytest.mark.asyncio
    async def test_scrape_with_custom_timeout(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
        """Test scraping with custom timeout."""
        mock_response = Mock()
        mock_response.url = "https://example.com"
        mock_response.text = sample_html
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.encoding = "utf-8"
        mock_response.elapsed.total_seconds.return_value = 0.5

        async def mock_executor(executor, func):
            return func()

        with patch.object(provider.session, "get", return_value=mock_response) as mock_get:
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_executor
                result = await provider.scrape("https://example.com", timeout=30)

                # Verify custom timeout was used
                call_args = mock_get.call_args
                assert call_args[1]["timeout"] == 30

    @pytest.mark.asyncio
    async def test_scrape_with_custom_headers(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
        """Test scraping with custom headers."""
        mock_response = Mock()
        mock_response.url = "https://example.com"
        mock_response.text = sample_html
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.encoding = "utf-8"
        mock_response.elapsed.total_seconds.return_value = 0.1

        custom_headers = {
            "User-Agent": "CustomBot/1.0",
            "Accept-Language": "en-US",
        }

        async def mock_executor(executor, func):
            return func()

        with patch.object(provider.session, "get", return_value=mock_response) as mock_get:
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_executor
                result = await provider.scrape("https://example.com", headers=custom_headers)

                # Verify custom headers were used
                call_args = mock_get.call_args
                assert call_args[1]["headers"]["User-Agent"] == "CustomBot/1.0"
                assert call_args[1]["headers"]["Accept-Language"] == "en-US"

    @pytest.mark.asyncio
    async def test_scrape_http_error(self, provider: RequestsProvider) -> None:
        """Test scraping with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 404
        error = requests.HTTPError("404 Not Found", response=mock_response)
        mock_response.raise_for_status.side_effect = error

        with patch.object(provider.session, "get", return_value=mock_response) as mock_get:
            with pytest.raises(requests.HTTPError):
                await provider.scrape("https://example.com/not-found")

        mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrape_connection_error(self, provider: RequestsProvider) -> None:
        """Test scraping with connection error."""
        with patch.object(
            provider.session,
            "get",
            side_effect=requests.ConnectionError("Connection failed"),
        ):
            with pytest.raises(requests.ConnectionError):
                await provider.scrape("https://unreachable.example.com")

    @pytest.mark.asyncio
    async def test_scrape_timeout_error(self, provider: RequestsProvider) -> None:
        """Test scraping with timeout error."""
        with patch.object(
            provider.session, "get", side_effect=requests.Timeout("Request timed out")
        ):
            with pytest.raises(requests.Timeout):
                await provider.scrape("https://slow.example.com")

    @pytest.mark.asyncio
    async def test_scrape_redirect_followed(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
        """Test that redirects are followed and final URL is returned."""
        mock_response = Mock()
        mock_response.url = "https://example.com/final"  # Final URL after redirect
        mock_response.text = sample_html
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.encoding = "utf-8"
        mock_response.elapsed.total_seconds.return_value = 0.2

        async def mock_executor(executor, func):
            return func()

        with patch.object(provider.session, "get", return_value=mock_response):
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_executor
                result = await provider.scrape("https://example.com/redirect")

                # Should return the final URL after redirect
                assert result.url == "https://example.com/final"

    @pytest.mark.asyncio
    async def test_default_user_agent(self, provider: RequestsProvider, sample_html: str) -> None:
        """Test that default user agent is used."""
        mock_response = Mock()
        mock_response.url = "https://example.com"
        mock_response.text = sample_html
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.encoding = "utf-8"
        mock_response.elapsed.total_seconds.return_value = 0.1

        async def mock_executor(executor, func):
            return func()

        with patch.object(provider.session, "get", return_value=mock_response) as mock_get:
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_executor
                await provider.scrape("https://example.com")

                # Verify default user agent was used
                call_args = mock_get.call_args
                user_agent = call_args[1]["headers"]["User-Agent"]
                assert "Mozilla" in user_agent or "Chrome" in user_agent

    @pytest.mark.asyncio
    async def test_metadata_includes_headers(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
        """Test that metadata includes response headers."""
        mock_response = Mock()
        mock_response.url = "https://example.com"
        mock_response.text = sample_html
        mock_response.status_code = 200
        mock_response.headers = {
            "Content-Type": "text/html; charset=utf-8",
            "Server": "nginx/1.18.0",
            "X-Custom-Header": "test-value",
        }
        mock_response.encoding = "utf-8"
        mock_response.elapsed.total_seconds.return_value = 0.15

        async def mock_executor(executor, func):
            return func()

        with patch.object(provider.session, "get", return_value=mock_response):
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_executor
                result = await provider.scrape("https://example.com")

                # Verify headers are in metadata
                assert "headers" in result.metadata
                assert result.metadata["headers"]["Server"] == "nginx/1.18.0"
                assert result.metadata["headers"]["X-Custom-Header"] == "test-value"

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, provider: RequestsProvider, sample_html: str) -> None:
        """Test that provider retries on timeout."""
        mock_response = Mock()
        mock_response.url = "https://example.com"
        mock_response.text = sample_html
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.encoding = "utf-8"
        mock_response.elapsed.total_seconds.return_value = 0.1

        async def mock_executor(executor, func):
            return func()

        # First two calls timeout, third succeeds
        with patch.object(
            provider.session,
            "get",
            side_effect=[
                requests.Timeout("Timeout 1"),
                requests.Timeout("Timeout 2"),
                mock_response,
            ],
        ):
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_executor
                result = await provider.scrape("https://example.com", max_retries=3)

                # Should succeed after retries
                assert result.status_code == 200
                assert result.metadata["attempts"] == 3
                assert result.metadata["retries"] == 2

    @pytest.mark.asyncio
    async def test_retry_on_transient_http_error(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
        """Test that transient HTTP failures are retried."""
        transient_response = Mock()
        transient_response.status_code = 503
        transient_response.raise_for_status.side_effect = requests.HTTPError(
            "503 Service Unavailable", response=transient_response
        )

        success_response = Mock()
        success_response.url = "https://example.com"
        success_response.text = sample_html
        success_response.status_code = 200
        success_response.headers = {"Content-Type": "text/html"}
        success_response.elapsed.total_seconds.return_value = 0.1

        with (
            patch.object(
                provider.session,
                "get",
                side_effect=[transient_response, success_response],
            ) as mock_get,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result = await provider.scrape("https://example.com", max_retries=1)

        assert result.status_code == 200
        assert result.metadata["attempts"] == 2
        assert mock_get.call_count == 2
        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, provider: RequestsProvider) -> None:
        """Test that provider raises after exhausting retries."""
        with patch.object(
            provider.session,
            "get",
            side_effect=requests.Timeout("Always timeout"),
        ):
            with pytest.raises(requests.Timeout):
                await provider.scrape("https://example.com", max_retries=2)

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
        """Test retry on connection errors."""
        mock_response = Mock()
        mock_response.url = "https://example.com"
        mock_response.text = sample_html
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.encoding = "utf-8"
        mock_response.elapsed.total_seconds.return_value = 0.1

        async def mock_executor(executor, func):
            return func()

        # First call fails, second succeeds
        with patch.object(
            provider.session,
            "get",
            side_effect=[
                requests.ConnectionError("Connection failed"),
                mock_response,
            ],
        ):
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_executor
                result = await provider.scrape("https://example.com")

                assert result.status_code == 200
                assert result.metadata["attempts"] == 2
                assert result.metadata["retries"] == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_success(self, provider: RequestsProvider, sample_html: str) -> None:
        """Test that no retries occur on immediate success."""
        mock_response = Mock()
        mock_response.url = "https://example.com"
        mock_response.text = sample_html
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.encoding = "utf-8"
        mock_response.elapsed.total_seconds.return_value = 0.1

        async def mock_executor(executor, func):
            return func()

        with patch.object(provider.session, "get", return_value=mock_response) as mock_get:
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_executor
                result = await provider.scrape("https://example.com")

                # Should only call once
                mock_get.assert_called_once()
                assert result.metadata["attempts"] == 1
                assert result.metadata["retries"] == 0

    @pytest.mark.asyncio
    async def test_custom_max_retries(self, provider: RequestsProvider, sample_html: str) -> None:
        """Test custom max_retries parameter."""
        mock_response = Mock()
        mock_response.url = "https://example.com"
        mock_response.text = sample_html
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.encoding = "utf-8"
        mock_response.elapsed.total_seconds.return_value = 0.1

        async def mock_executor(executor, func):
            return func()

        # Fail 4 times, succeed on 5th
        with patch.object(
            provider.session,
            "get",
            side_effect=[
                requests.Timeout("Fail 1"),
                requests.Timeout("Fail 2"),
                requests.Timeout("Fail 3"),
                requests.Timeout("Fail 4"),
                mock_response,
            ],
        ):
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = mock_executor
                result = await provider.scrape("https://example.com", max_retries=5)

                assert result.status_code == 200
                assert result.metadata["attempts"] == 5
                assert result.metadata["retries"] == 4


class TestPlaywrightProvider:
    """Tests for PlaywrightProvider."""

    def test_supports_http_urls(self) -> None:
        """Test that provider supports HTTP/HTTPS URLs."""
        provider = PlaywrightProvider()
        assert provider.supports_url("http://example.com")
        assert provider.supports_url("https://example.com")
        assert provider.supports_url("https://example.com/path?query=1")

    def test_rejects_non_http_urls(self) -> None:
        """Test that provider rejects non-HTTP URLs."""
        provider = PlaywrightProvider()
        assert not provider.supports_url("ftp://example.com")
        assert not provider.supports_url("file:///path/to/file")
        assert not provider.supports_url("javascript:alert('test')")
        assert not provider.supports_url("data:text/html,<h1>Test</h1>")

    def test_rejects_invalid_urls(self) -> None:
        """Test that provider rejects invalid URLs."""
        provider = PlaywrightProvider()
        assert not provider.supports_url("not a url")
        assert not provider.supports_url("")
        assert not provider.supports_url("://invalid")

    def test_default_configuration(self) -> None:
        """Test default provider configuration."""
        provider = PlaywrightProvider()
        assert provider.timeout == 30000
        assert provider.wait_until == "networkidle"

    def test_custom_configuration(self) -> None:
        """Test custom provider configuration."""
        provider = PlaywrightProvider(timeout=60000, wait_until="domcontentloaded")
        assert provider.timeout == 60000
        assert provider.wait_until == "domcontentloaded"

    @pytest.mark.asyncio
    async def test_scrape_success(self, sample_html: str) -> None:
        """Test successful scraping with mocked browser."""
        provider = PlaywrightProvider()

        # Mock the browser pool and context
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.content = AsyncMock(return_value=sample_html)
        mock_page.close = AsyncMock()
        mock_page.set_default_timeout = Mock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_page.goto = AsyncMock(return_value=mock_response)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_pool = AsyncMock()
        mock_pool.acquire_context = AsyncMock(return_value=mock_context)
        mock_pool.release_context = AsyncMock()

        with patch.object(provider, "_pool", mock_pool):
            result = await provider.scrape("https://example.com")

            assert isinstance(result, ScrapeResult)
            assert result.url == "https://example.com"
            assert result.content == sample_html
            assert result.status_code == 200
            assert result.metadata["rendered_js"] is True
            mock_pool.acquire_context.assert_called_once()
            mock_pool.release_context.assert_called_once_with(mock_context)

    @pytest.mark.asyncio
    async def test_scrape_with_custom_timeout(self, sample_html: str) -> None:
        """Test scraping with custom timeout."""
        provider = PlaywrightProvider()

        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.content = AsyncMock(return_value=sample_html)
        mock_page.close = AsyncMock()
        mock_page.set_default_timeout = Mock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_page.goto = AsyncMock(return_value=mock_response)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_pool = AsyncMock()
        mock_pool.acquire_context = AsyncMock(return_value=mock_context)
        mock_pool.release_context = AsyncMock()

        with patch.object(provider, "_pool", mock_pool):
            await provider.scrape("https://example.com", timeout=60000)

            mock_page.set_default_timeout.assert_called_with(60000)

    @pytest.mark.asyncio
    async def test_scrape_with_wait_for_selector(self, sample_html: str) -> None:
        """Test scraping with wait_for_selector option."""
        provider = PlaywrightProvider()

        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.content = AsyncMock(return_value=sample_html)
        mock_page.close = AsyncMock()
        mock_page.set_default_timeout = Mock()
        mock_page.wait_for_selector = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_page.goto = AsyncMock(return_value=mock_response)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_pool = AsyncMock()
        mock_pool.acquire_context = AsyncMock(return_value=mock_context)
        mock_pool.release_context = AsyncMock()

        with patch.object(provider, "_pool", mock_pool):
            result = await provider.scrape("https://example.com", wait_for_selector="#main-content")

            mock_page.wait_for_selector.assert_called_once()
            assert result.metadata.get("wait_for_selector") == "#main-content"

    @pytest.mark.asyncio
    async def test_scrape_cleanup_on_error(self) -> None:
        """Test that context is released even on error."""
        provider = PlaywrightProvider()

        mock_page = AsyncMock()
        mock_page.close = AsyncMock()
        mock_page.set_default_timeout = Mock()
        mock_page.goto = AsyncMock(side_effect=Exception("Navigation failed"))

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_pool = AsyncMock()
        mock_pool.acquire_context = AsyncMock(return_value=mock_context)
        mock_pool.release_context = AsyncMock()

        with patch.object(provider, "_pool", mock_pool):
            with pytest.raises(RuntimeError, match="Playwright failed"):
                await provider.scrape("https://example.com")

            # Context should still be released even after error
            mock_pool.release_context.assert_called_once_with(mock_context)

    @pytest.mark.asyncio
    async def test_scrape_follows_redirects(self, sample_html: str) -> None:
        """Test that final URL after redirects is captured."""
        provider = PlaywrightProvider()

        mock_page = AsyncMock()
        mock_page.url = "https://example.com/final-page"  # Final URL after redirect
        mock_page.content = AsyncMock(return_value=sample_html)
        mock_page.close = AsyncMock()
        mock_page.set_default_timeout = Mock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_page.goto = AsyncMock(return_value=mock_response)

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_pool = AsyncMock()
        mock_pool.acquire_context = AsyncMock(return_value=mock_context)
        mock_pool.release_context = AsyncMock()

        with patch.object(provider, "_pool", mock_pool):
            result = await provider.scrape("https://example.com/redirect")

            assert result.url == "https://example.com/final-page"
            assert result.metadata["final_url"] == "https://example.com/final-page"


class TestBrowserPoolManager:
    """Tests for BrowserPoolManager."""

    def test_singleton_pattern(self) -> None:
        """Test that BrowserPoolManager is a singleton."""
        # Reset singleton for test
        BrowserPoolManager._instance = None

        pool1 = BrowserPoolManager()
        pool2 = BrowserPoolManager()

        assert pool1 is pool2

        # Cleanup
        BrowserPoolManager._instance = None

    def test_default_configuration(self) -> None:
        """Test default pool configuration."""
        BrowserPoolManager._instance = None

        with patch.dict("os.environ", {}, clear=True):
            pool = BrowserPoolManager()
            assert pool.max_contexts == 5
            assert pool.timeout == 30000
            assert pool.disable_gpu is True

        BrowserPoolManager._instance = None

    def test_custom_configuration_from_env(self) -> None:
        """Test pool configuration from environment variables."""
        BrowserPoolManager._instance = None

        with patch.dict(
            "os.environ",
            {
                "PLAYWRIGHT_MAX_CONTEXTS": "10",
                "PLAYWRIGHT_TIMEOUT": "60000",
                "PLAYWRIGHT_DISABLE_GPU": "false",
            },
        ):
            pool = BrowserPoolManager()
            assert pool.max_contexts == 10
            assert pool.timeout == 60000
            assert pool.disable_gpu is False

        BrowserPoolManager._instance = None

    def test_is_initialized_before_browser_start(self) -> None:
        """Test is_initialized returns False before browser starts."""
        BrowserPoolManager._instance = None

        pool = BrowserPoolManager()
        assert pool.is_initialized is False

        BrowserPoolManager._instance = None

    def test_active_contexts_tracking(self) -> None:
        """Test that active contexts are tracked."""
        BrowserPoolManager._instance = None

        pool = BrowserPoolManager()
        assert pool.active_contexts == 0

        BrowserPoolManager._instance = None


class TestPlaywrightAvailability:
    """Tests for Playwright availability checking."""

    def test_is_playwright_available_returns_bool(self) -> None:
        """Test is_playwright_available returns a boolean."""
        # The function should return True or False depending on installation
        result = is_playwright_available()
        assert isinstance(result, bool)

    def test_is_playwright_available_handles_import_error(self) -> None:
        """Test is_playwright_available handles ImportError gracefully."""
        # Test the function's behavior when playwright cannot be imported
        # by temporarily removing it from sys.modules
        import builtins
        import importlib
        import sys

        original_modules = sys.modules.copy()

        # Remove playwright from sys.modules if present
        modules_to_remove = [k for k in sys.modules if k.startswith("playwright")]
        for mod in modules_to_remove:
            del sys.modules[mod]

        # Mock the import to raise ImportError
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "playwright" or name.startswith("playwright."):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        try:
            builtins.__import__ = mock_import
            # The actual function should handle this gracefully
            # We're testing that it doesn't crash
            from scraper_mcp.providers import playwright_provider

            # Reload to test fresh import behavior
            importlib.reload(playwright_provider)
        except ImportError:
            pass  # Expected when playwright is not installed
        finally:
            builtins.__import__ = original_import
            # Restore original modules
            sys.modules.update(original_modules)


class TestGetBrowserPool:
    """Tests for get_browser_pool function."""

    def test_returns_singleton_instance(self) -> None:
        """Test that get_browser_pool returns singleton instance."""
        # Reset global state
        import scraper_mcp.providers.playwright_provider as pw_module

        pw_module._browser_pool = None
        pw_module.BrowserPoolManager._instance = None

        pool1 = get_browser_pool()
        pool2 = get_browser_pool()

        assert pool1 is pool2
        # Use type name comparison to avoid import identity issues
        assert type(pool1).__name__ == "BrowserPoolManager"

        # Cleanup
        pw_module._browser_pool = None
        pw_module.BrowserPoolManager._instance = None
