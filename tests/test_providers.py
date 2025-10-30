"""Tests for scraper providers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
import requests

from scraper_mcp.providers import RequestsProvider, ScrapeResult


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
    async def test_scrape_success(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
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
                result = await provider.scrape(
                    "https://example.com", headers=custom_headers
                )

                # Verify custom headers were used
                call_args = mock_get.call_args
                assert call_args[1]["headers"]["User-Agent"] == "CustomBot/1.0"
                assert call_args[1]["headers"]["Accept-Language"] == "en-US"

    @pytest.mark.asyncio
    async def test_scrape_http_error(self, provider: RequestsProvider) -> None:
        """Test scraping with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

        with patch.object(provider.session, "get", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                await provider.scrape("https://example.com/not-found")

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
        with patch.object(provider.session, "get", side_effect=requests.Timeout("Request timed out")):
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
    async def test_default_user_agent(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
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
    async def test_retry_on_timeout(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
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
    async def test_no_retry_on_success(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
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
    async def test_custom_max_retries(
        self, provider: RequestsProvider, sample_html: str
    ) -> None:
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
