"""Integration tests for MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from scraper_mcp.cache import clear_all_cache, clear_expired_cache, get_cache_stats
from scraper_mcp.providers import ScrapeResult
from scraper_mcp.server import (
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

            result = await scrape_url(["https://example.com"])

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1
            assert result.results[0].data.url == "https://example.com"
            assert result.results[0].data.content == sample_html
            assert result.results[0].data.status_code == 200
            assert result.results[0].data.content_type == "text/html; charset=utf-8"
            assert "encoding" in result.results[0].data.metadata

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

            result = await scrape_url(["https://example.com"], timeout=60)

            # Verify scrape was called with custom timeout and default retries
            mock_provider.scrape.assert_called_once_with(
                "https://example.com", timeout=60, max_retries=3
            )
            assert result.total == 1
            assert result.successful == 1

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

            result = await scrape_url(["https://example.com"], max_retries=5)

            # Verify scrape was called with custom retries
            mock_provider.scrape.assert_called_once_with(
                "https://example.com", timeout=30, max_retries=5
            )

            # Verify metadata includes retry info
            assert result.results[0].data.metadata["attempts"] == 2
            assert result.results[0].data.metadata["retries"] == 1


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

            result = await scrape_url_markdown(["https://example.com"])

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Content should be markdown, not HTML
            assert "Main Heading" in result.results[0].data.content
            assert "<html>" not in result.results[0].data.content
            assert "<body>" not in result.results[0].data.content

            # Should have page metadata
            assert "page_metadata" in result.results[0].data.metadata
            assert result.results[0].data.metadata["page_metadata"]["title"] == "Test Page Title"

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
                ["https://example.com"], strip_tags=["script", "style"]
            )

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Scripts and styles should be stripped
            assert "console.log" not in result.results[0].data.content
            assert ".test { color: red; }" not in result.results[0].data.content
            # But content should remain
            assert "Main Heading" in result.results[0].data.content

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

            result = await scrape_url_markdown(["https://example.com"])

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Should extract metadata
            page_metadata = result.results[0].data.metadata["page_metadata"]
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

            result = await scrape_url_text(["https://example.com"])

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Content should be plain text
            assert "Main Heading" in result.results[0].data.content
            assert "sample" in result.results[0].data.content and "paragraph" in result.results[0].data.content
            # No HTML tags
            assert "<html>" not in result.results[0].data.content
            assert "<body>" not in result.results[0].data.content
            assert "<p>" not in result.results[0].data.content

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

            result = await scrape_url_text(["https://example.com"])

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Scripts, styles, etc. should be stripped by default
            assert "console.log" not in result.results[0].data.content
            assert ".test { color: red; }" not in result.results[0].data.content
            assert "No JavaScript content" not in result.results[0].data.content

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
                ["https://example.com"], strip_tags=["script", "ul"]
            )

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Custom tags should be stripped
            assert "console.log" not in result.results[0].data.content
            # ul stripped, so links should not appear
            assert "Example Link" not in result.results[0].data.content


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

            result = await scrape_extract_links(["https://example.com/page"])

            # Should return BatchLinksResponse
            assert result.total == 1
            assert result.successful == 1
            assert result.results[0].data.url == "https://example.com/page"
            assert result.results[0].data.count == 5  # Should find 5 links
            assert len(result.results[0].data.links) == 5

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

            result = await scrape_extract_links(["https://example.com/page"])

            # Should return BatchLinksResponse
            assert result.total == 1
            assert result.successful == 1

            # Check that links have required fields
            for link in result.results[0].data.links:
                assert "url" in link
                assert "text" in link
                assert "title" in link

            # Check specific links
            external_link = next(
                (l for l in result.results[0].data.links if l["text"] == "External Link"), None
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

            result = await scrape_extract_links(["https://example.com/page"])

            # Should return BatchLinksResponse
            assert result.total == 1
            assert result.successful == 1

            # Relative URLs should be resolved
            relative_link = next(
                (l for l in result.results[0].data.links if "/relative/path" in l["url"]), None
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

            result = await scrape_extract_links(["https://example.com"])

            # Should return BatchLinksResponse
            assert result.total == 1
            assert result.successful == 1
            assert result.results[0].data.count == 0
            assert len(result.results[0].data.links) == 0


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


class TestCssSelectorFiltering:
    """Tests for CSS selector filtering across all tools."""

    @pytest.mark.asyncio
    async def test_scrape_url_with_css_selector(
        self, html_with_structured_content: str
    ) -> None:
        """Test scrape_url with CSS selector filtering."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=html_with_structured_content,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url(["https://example.com"], css_selector="meta")

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Should only contain meta tags
            assert "<meta" in result.results[0].data.content
            assert "<article" not in result.results[0].data.content
            # Should have filter metadata
            assert "css_selector_applied" in result.results[0].data.metadata
            assert result.results[0].data.metadata["css_selector_applied"] == "meta"
            assert result.results[0].data.metadata["elements_matched"] == 3

    @pytest.mark.asyncio
    async def test_scrape_url_markdown_with_css_selector(
        self, html_with_structured_content: str
    ) -> None:
        """Test markdown conversion with CSS selector."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=html_with_structured_content,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url_markdown(
                ["https://example.com"], css_selector=".main-content"
            )

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Should only contain article content in markdown
            assert "Article Title" in result.results[0].data.content
            assert "Footer content" not in result.results[0].data.content
            # Should have filter metadata
            assert "css_selector_applied" in result.results[0].data.metadata
            assert result.results[0].data.metadata["css_selector_applied"] == ".main-content"

    @pytest.mark.asyncio
    async def test_scrape_url_text_with_css_selector(
        self, html_with_structured_content: str
    ) -> None:
        """Test text extraction with CSS selector."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=html_with_structured_content,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url_text(
                ["https://example.com"], css_selector="article"
            )

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Should only contain article text
            assert "Article Title" in result.results[0].data.content
            assert "Article paragraph" in result.results[0].data.content
            assert "Footer content" not in result.results[0].data.content

    @pytest.mark.asyncio
    async def test_extract_links_with_css_selector(
        self, html_with_structured_content: str
    ) -> None:
        """Test link extraction with CSS selector scoping."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=html_with_structured_content,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_extract_links(
                ["https://example.com"], css_selector="nav"
            )

            # Should return BatchLinksResponse
            assert result.total == 1
            assert result.successful == 1

            # Should only contain nav links
            assert result.results[0].data.count == 2  # Home and About links only
            assert any(l["text"] == "Home" for l in result.results[0].data.links)
            assert any(l["text"] == "About" for l in result.results[0].data.links)
            assert not any(l["text"] == "Advertisement" for l in result.results[0].data.links)

    @pytest.mark.asyncio
    async def test_css_selector_with_multiple_elements(
        self, html_with_structured_content: str
    ) -> None:
        """Test CSS selector that matches multiple elements."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=html_with_structured_content,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url(["https://example.com"], css_selector="img, video")

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Should contain both img and video tags
            assert "<img" in result.results[0].data.content
            assert "<video" in result.results[0].data.content
            assert result.results[0].data.metadata["elements_matched"] == 2

    @pytest.mark.asyncio
    async def test_css_selector_no_matches(
        self, html_with_structured_content: str
    ) -> None:
        """Test CSS selector that matches nothing."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=html_with_structured_content,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            result = await scrape_url(
                ["https://example.com"], css_selector=".nonexistent"
            )

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Should return empty content
            assert result.results[0].data.content == ""
            assert result.results[0].data.metadata["elements_matched"] == 0

    @pytest.mark.asyncio
    async def test_css_selector_with_strip_tags(
        self, html_with_structured_content: str
    ) -> None:
        """Test CSS selector combined with strip_tags."""
        mock_result = ScrapeResult(
            url="https://example.com",
            content=html_with_structured_content,
            status_code=200,
            content_type="text/html",
            metadata={},
        )

        with patch("scraper_mcp.server.get_provider") as mock_get_provider:
            mock_provider = Mock()
            mock_provider.scrape = AsyncMock(return_value=mock_result)
            mock_get_provider.return_value = mock_provider

            # First filter to article, then strip img tags
            result = await scrape_url_markdown(
                ["https://example.com"],
                css_selector="article",
                strip_tags=["img", "video"],
            )

            # Should return BatchScrapeResponse
            assert result.total == 1
            assert result.successful == 1

            # Should have article content but no images/videos
            assert "Article Title" in result.results[0].data.content
            assert "Article paragraph" in result.results[0].data.content
            # Images and videos should be stripped from markdown
            assert "![" not in result.results[0].data.content or "article-image.jpg" not in result.results[0].data.content


class TestCacheManagementTools:
    """Tests for cache management tools."""

    def test_cache_stats_available(self) -> None:
        """Test getting cache statistics when cache is available."""
        result = get_cache_stats()

        # Should return cache statistics
        assert isinstance(result, dict)
        assert "size_bytes" in result or "error" in result

    def test_cache_clear_expired_available(self) -> None:
        """Test clearing expired cache entries."""
        removed = clear_expired_cache()

        # Should return integer count of removed entries
        assert isinstance(removed, int)
        assert removed >= 0

    def test_cache_clear_all_available(self) -> None:
        """Test clearing all cache entries."""
        # Should not raise any exceptions
        clear_all_cache()
        # If we get here, it worked
