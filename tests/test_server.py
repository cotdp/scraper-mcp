"""Integration tests for MCP server tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

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

            # Verify scrape was called with custom timeout
            mock_provider.scrape.assert_called_once_with(
                "https://example.com", timeout=60
            )


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
