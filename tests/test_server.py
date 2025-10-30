"""Integration tests for MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from scraper_mcp.providers import ScrapeResult
from scraper_mcp.server import (
    cache_clear_all,
    cache_clear_expired,
    cache_stats,
    scrape_extract_links,
    scrape_url,
    scrape_url_markdown,
    scrape_url_text,
)


class TestScrapeUrlTool:
    """Tests for scrape_url tool."""

    @pytest.mark.asyncio
    async def test_scrape_url_success(self, sample_html: str) -> None:
        """Test successful URL scraping."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html; charset=utf-8",
            metadata={"headers": {}, "encoding": "utf-8", "elapsed_ms": 123.45},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url("https://example.com")

            assert result.url == "https://example.com"
            assert result.content == sample_html
            assert result.status_code == 200
            assert result.content_type == "text/html; charset=utf-8"
            assert "encoding" in result.metadata

    @pytest.mark.asyncio
    async def test_scrape_url_with_timeout(self, sample_html: str) -> None:
        """Test scraping with custom timeout."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url("https://example.com", timeout=60)

            # Verify scrape was called with custom timeout and default retries
            mock_provider.scrape.assert_called_once_with(
                "https://example.com", timeout=60, max_retries=3
            )

    @pytest.mark.asyncio
    async def test_scrape_url_with_retries(self, sample_html: str) -> None:
        """Test scraping with custom max_retries."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={"attempts": 2, "retries": 1},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url("https://example.com", max_retries=5)

            # Verify scrape was called with custom retries
            mock_provider.scrape.assert_called_once_with(
                "https://example.com", timeout=30, max_retries=5
            )

            # Verify metadata includes retry info
            assert result.metadata["attempts"] == 2
            assert result.metadata["retries"] == 1


class TestScrapeUrlMarkdownTool:
    """Tests for scrape_url_markdown tool."""

    @pytest.mark.asyncio
    async def test_scrape_url_markdown_conversion(self, sample_html: str) -> None:
        """Test HTML to markdown conversion."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url_markdown("https://example.com")

            # Content should be markdown, not HTML
            assert "Main Heading" in result.content
            assert "<html>" not in result.content
            assert "<body>" not in result.content

            # Should have page metadata
            assert "page_metadata" in result.metadata
            assert result.metadata["page_metadata"]["title"] == "Test Page Title"

    @pytest.mark.asyncio
    async def test_scrape_url_markdown_strip_tags(self, sample_html: str) -> None:
        """Test markdown conversion with tag stripping."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url_markdown(
                "https://example.com", strip_tags=["script", "style"]
            )

            # Scripts and styles should be stripped
            assert "console.log" not in result.content
            assert ".test { color: red; }" not in result.content
            # But content should remain
            assert "Main Heading" in result.content

    @pytest.mark.asyncio
    async def test_scrape_url_markdown_metadata_extraction(
        self, html_with_metadata: str
    ) -> None:
        """Test that page metadata is extracted."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=html_with_metadata,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url_markdown("https://example.com")

            # Should extract metadata
            page_metadata = result.metadata["page_metadata"]
            assert page_metadata["title"] == "Metadata Test Page"
            assert page_metadata["description"] == "Test description"
            assert page_metadata["og:title"] == "OG Title"


class TestScrapeUrlTextTool:
    """Tests for scrape_url_text tool."""

    @pytest.mark.asyncio
    async def test_scrape_url_text_extraction(self, sample_html: str) -> None:
        """Test plain text extraction."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url_text("https://example.com")

            # Content should be plain text
            assert "Main Heading" in result.content
            assert "sample" in result.content and "paragraph" in result.content
            # No HTML tags
            assert "<html>" not in result.content
            assert "<body>" not in result.content
            assert "<p>" not in result.content

    @pytest.mark.asyncio
    async def test_scrape_url_text_default_stripping(self, sample_html: str) -> None:
        """Test that default tags are stripped."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url_text("https://example.com")

            # Scripts, styles, etc. should be stripped by default
            assert "console.log" not in result.content
            assert ".test { color: red; }" not in result.content
            assert "No JavaScript content" not in result.content

    @pytest.mark.asyncio
    async def test_scrape_url_text_custom_stripping(self, sample_html: str) -> None:
        """Test text extraction with custom tag stripping."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url_text(
                "https://example.com", strip_tags=["script", "ul"]
            )

            # Custom tags should be stripped
            assert "console.log" not in result.content
            # ul stripped, so links should not appear
            assert "Example Link" not in result.content


class TestScrapeExtractLinksTool:
    """Tests for scrape_extract_links tool."""

    @pytest.mark.asyncio
    async def test_extract_links_basic(self, html_with_links: str) -> None:
        """Test basic link extraction."""
        mock_result = ScrapeResult(
            url="https://example.com/page",
            content=html_with_links,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_extract_links("https://example.com/page")

            assert result.url == "https://example.com/page"
            assert result.count == 5  # Should find 5 links
            assert len(result.links) == 5

    @pytest.mark.asyncio
    async def test_extract_links_details(self, html_with_links: str) -> None:
        """Test that link details are extracted."""
        mock_result = ScrapeResult(
            url="https://example.com/page",
            content=html_with_links,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_extract_links("https://example.com/page")

            # Check that links have required fields
            for link in result.links:
                assert "url" in link
                assert "text" in link
                assert "title" in link

            # Check specific links
            external_link = next(
                (l for l in result.links if l["text"] == "External Link"), None
            )
            assert external_link is not None
            assert external_link["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_extract_links_url_resolution(self, html_with_links: str) -> None:
        """Test that relative URLs are resolved."""
        mock_result = ScrapeResult(
            url="https://example.com/page",
            content=html_with_links,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_extract_links("https://example.com/page")

            # Relative URLs should be resolved
            relative_link = next(
                (l for l in result.links if "/relative/path" in l["url"]), None
            )
            assert relative_link is not None
            assert relative_link["url"] == "https://example.com/relative/path"

    @pytest.mark.asyncio
    async def test_extract_links_empty_page(self) -> None:
        """Test link extraction from page with no links."""
        empty_html = "<html><body><p>No links here</p></body></html>"
        mock_result = ScrapeResult(
            url="https://example.com",
            content=empty_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch(
            "scraper_mcp.server.get_provider"
        ) as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_extract_links("https://example.com")

            assert result.count == 0
            assert len(result.links) == 0


class TestBatchScrapeUrl:
    """Tests for batch scrape_url operations."""

    @pytest.mark.asyncio
    async def test_batch_scrape_multiple_urls(self, sample_html: str) -> None:
        """Test batch scraping multiple URLs."""
        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
        ]

        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url(urls)

            # Should return BatchScrapeResponse
            assert hasattr(result, "total")
            assert hasattr(result, "successful")
            assert hasattr(result, "failed")
            assert hasattr(result, "results")

            # Should have results for all URLs
            assert result.total == 3
            assert result.successful == 3
            assert result.failed == 0
            assert len(result.results) == 3

    @pytest.mark.asyncio
    async def test_batch_scrape_partial_failure(self, sample_html: str) -> None:
        """Test batch scraping with some URLs failing."""
        urls = [
            "https://example.com/success",
            "https://example.com/fail",
        ]

        mock_success = ScrapeResult(
            url="https://example.com/success",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            # First call succeeds, second fails
            mock_provider.scrape = AsyncMock(
                side_effect=[mock_success, Exception("Connection failed")]
            )
            mock_get_provider.return_value = mock_provider

            result = await scrape_url(urls)

            # Should have mixed results
            assert result.total == 2
            assert result.successful == 1
            assert result.failed == 1

            # First result should be successful
            assert result.results[0].success is True
            assert result.results[0].data is not None

            # Second result should have error
            assert result.results[1].success is False
            assert result.results[1].error is not None

    @pytest.mark.asyncio
    async def test_batch_scrape_single_url_backward_compat(
        self, sample_html: str
    ) -> None:
        """Test that single URL still works (backward compatibility)."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url("https://example.com")

            # Should return ScrapeResponse, not BatchScrapeResponse
            assert hasattr(result, "url")
            assert hasattr(result, "content")
            assert not hasattr(result, "total")


class TestBatchScrapeUrlMarkdown:
    """Tests for batch scrape_url_markdown operations."""

    @pytest.mark.asyncio
    async def test_batch_markdown_multiple_urls(self, sample_html: str) -> None:
        """Test batch markdown conversion for multiple URLs."""
        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
        ]

        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url_markdown(urls)

            # Should return BatchScrapeResponse
            assert result.total == 2
            assert result.successful == 2
            assert result.failed == 0

            # Check that content is markdown
            for item in result.results:
                assert item.success is True
                assert "Main Heading" in item.data.content
                assert "<html>" not in item.data.content


class TestBatchScrapeUrlText:
    """Tests for batch scrape_url_text operations."""

    @pytest.mark.asyncio
    async def test_batch_text_multiple_urls(self, sample_html: str) -> None:
        """Test batch text extraction for multiple URLs."""
        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
        ]

        mock_result = ScrapeResult(
            url="https://example.com",
            content=sample_html,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url_text(urls)

            # Should return BatchScrapeResponse
            assert result.total == 2
            assert result.successful == 2
            assert result.failed == 0

            # Check that content is plain text
            for item in result.results:
                assert item.success is True
                assert "Main Heading" in item.data.content
                assert "<html>" not in item.data.content


class TestBatchExtractLinks:
    """Tests for batch scrape_extract_links operations."""

    @pytest.mark.asyncio
    async def test_batch_extract_links_multiple_urls(
        self, html_with_links: str
    ) -> None:
        """Test batch link extraction for multiple URLs."""
        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
        ]

        mock_result = ScrapeResult(
            url="https://example.com/page",
            content=html_with_links,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_extract_links(urls)

            # Should return BatchLinksResponse
            assert hasattr(result, "total")
            assert hasattr(result, "successful")
            assert hasattr(result, "results")

            assert result.total == 2
            assert result.successful == 2
            assert result.failed == 0

            # Check that links were extracted
            for item in result.results:
                assert item.success is True
                assert item.data.count == 5
                assert len(item.data.links) == 5


class TestCacheManagementTools:
    """Tests for cache management tools."""

    @pytest.mark.asyncio
    async def test_cache_stats_available(self) -> None:
        """Test getting cache statistics when cache is available."""
        result = await cache_stats()

        # Should return cache statistics
        assert "total_responses" in result or "error" in result

        # If cache is available, check for expected fields
        if "total_responses" in result:
            assert "cache_size_bytes" in result
            assert "cache_size_mb" in result
            assert "cache_path" in result

    @pytest.mark.asyncio
    async def test_cache_clear_expired_available(self) -> None:
        """Test clearing expired cache entries."""
        result = await cache_clear_expired()

        # Should return success or error status
        assert "status" in result

        # If cache is available, should have removed count
        if result["status"] == "success":
            assert "expired_entries_removed" in result
            assert isinstance(result["expired_entries_removed"], int)

    @pytest.mark.asyncio
    async def test_cache_clear_all_available(self) -> None:
        """Test clearing all cache entries."""
        result = await cache_clear_all()

        # Should return status
        assert "status" in result
        assert "message" in result

        # Status should be success or error
        assert result["status"] in ["success", "error"]
