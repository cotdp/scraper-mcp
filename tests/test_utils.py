"""Tests for HTML utility functions."""

from __future__ import annotations

import pytest

from scraper_mcp.utils import (
    extract_links,
    extract_metadata,
    filter_html_by_selector,
    html_to_markdown,
    html_to_text,
)


class TestHtmlToMarkdown:
    """Tests for html_to_markdown function."""

    def test_basic_conversion(self, simple_html: str) -> None:
        """Test basic HTML to markdown conversion."""
        result = html_to_markdown(simple_html)

        assert "# Hello World" in result
        assert "This is a simple test." in result

    def test_strip_tags(self, sample_html: str) -> None:
        """Test stripping specific tags."""
        result = html_to_markdown(sample_html, strip_tags=["script", "style", "noscript"])

        assert "console.log" not in result
        assert ".test { color: red; }" not in result
        assert "No JavaScript content" not in result
        assert "Main Heading" in result

    def test_formatting_preserved(self, sample_html: str) -> None:
        """Test that text formatting is preserved in markdown."""
        result = html_to_markdown(sample_html)

        assert "**sample**" in result or "<strong>sample</strong>" in result
        assert "*formatting*" in result or "<em>formatting</em>" in result

    def test_links_preserved(self, html_with_links: str) -> None:
        """Test that links are preserved in markdown."""
        result = html_to_markdown(html_with_links)

        assert "https://example.com" in result
        assert "External Link" in result


class TestHtmlToText:
    """Tests for html_to_text function."""

    def test_basic_text_extraction(self, simple_html: str) -> None:
        """Test basic text extraction."""
        result = html_to_text(simple_html)

        assert "Simple Page" in result
        assert "Hello World" in result
        assert "This is a simple test." in result
        assert "<html>" not in result
        assert "<body>" not in result

    def test_default_tag_stripping(self, sample_html: str) -> None:
        """Test default tag stripping (script, style, etc.)."""
        result = html_to_text(sample_html)

        assert "console.log" not in result
        assert ".test { color: red; }" not in result
        assert "Main Heading" in result
        assert "sample" in result and "paragraph" in result

    def test_custom_tag_stripping(self, sample_html: str) -> None:
        """Test custom tag stripping."""
        result = html_to_text(sample_html, strip_tags=["script", "style", "ul"])

        assert "console.log" not in result
        assert "Example Link" not in result  # ul stripped
        assert "Main Heading" in result

    def test_text_formatting_removed(self, sample_html: str) -> None:
        """Test that HTML formatting is removed from text."""
        result = html_to_text(sample_html)

        assert "<strong>" not in result
        assert "<em>" not in result
        assert "sample" in result
        assert "formatting" in result

    def test_whitespace_handling(self, simple_html: str) -> None:
        """Test that excessive whitespace is cleaned up."""
        result = html_to_text(simple_html)
        lines = result.split("\n")

        # Should not have empty lines between content
        assert all(line.strip() for line in lines)


class TestExtractLinks:
    """Tests for extract_links function."""

    def test_basic_link_extraction(self, html_with_links: str) -> None:
        """Test basic link extraction."""
        links = extract_links(html_with_links)

        assert len(links) == 5  # Should find 5 links with href attributes
        assert any(link["url"] == "https://example.com" for link in links)
        assert any(link["url"] == "/relative/path" for link in links)

    def test_link_text_extraction(self, html_with_links: str) -> None:
        """Test that link text is extracted."""
        links = extract_links(html_with_links)

        link_texts = [link["text"] for link in links]
        assert "External Link" in link_texts
        assert "Relative Link" in link_texts

    def test_link_title_extraction(self, html_with_links: str) -> None:
        """Test that link titles are extracted."""
        links = extract_links(html_with_links)

        titled_link = next((link for link in links if link["title"] == "Page Title"), None)
        assert titled_link is not None
        assert titled_link["url"] == "https://example.com/page"

    def test_relative_url_resolution(self, html_with_links: str) -> None:
        """Test that relative URLs are resolved with base_url."""
        base_url = "https://example.com/page/test"
        links = extract_links(html_with_links, base_url=base_url)

        relative_link = next((link for link in links if "relative/path" in link["url"]), None)
        assert relative_link is not None
        assert relative_link["url"] == "https://example.com/relative/path"

    def test_anchor_links(self, html_with_links: str) -> None:
        """Test that anchor links are included."""
        links = extract_links(html_with_links)

        anchor_link = next((link for link in links if link["url"] == "#section"), None)
        assert anchor_link is not None
        assert anchor_link["text"] == "Anchor Link"

    def test_empty_href_ignored(self, html_with_links: str) -> None:
        """Test that links without href are ignored."""
        links = extract_links(html_with_links)

        # Should not include the link without href
        assert all(link["url"] for link in links)


class TestExtractMetadata:
    """Tests for extract_metadata function."""

    def test_title_extraction(self, html_with_metadata: str) -> None:
        """Test title extraction."""
        metadata = extract_metadata(html_with_metadata)

        assert metadata["title"] == "Metadata Test Page"

    def test_meta_name_extraction(self, html_with_metadata: str) -> None:
        """Test meta name tag extraction."""
        metadata = extract_metadata(html_with_metadata)

        assert metadata["description"] == "Test description"
        assert metadata["keywords"] == "test, metadata, html"

    def test_meta_property_extraction(self, html_with_metadata: str) -> None:
        """Test meta property (OpenGraph) extraction."""
        metadata = extract_metadata(html_with_metadata)

        assert metadata["og:title"] == "OG Title"
        assert metadata["og:description"] == "OG Description"
        assert metadata["og:image"] == "https://example.com/image.jpg"

    def test_twitter_card_extraction(self, html_with_metadata: str) -> None:
        """Test Twitter card metadata extraction."""
        metadata = extract_metadata(html_with_metadata)

        assert metadata["twitter:card"] == "summary"

    def test_missing_metadata(self, simple_html: str) -> None:
        """Test extraction from HTML with minimal metadata."""
        metadata = extract_metadata(simple_html)

        assert metadata["title"] == "Simple Page"
        # Should not have other metadata
        assert len(metadata) == 1

    def test_empty_html(self) -> None:
        """Test extraction from empty HTML."""
        metadata = extract_metadata("<html><body></body></html>")

        assert isinstance(metadata, dict)
        assert "title" not in metadata or metadata["title"] == ""


class TestFilterHtmlBySelector:
    """Tests for filter_html_by_selector function."""

    def test_filter_single_tag(self, html_with_structured_content: str) -> None:
        """Test filtering by single tag name."""
        result, count = filter_html_by_selector(html_with_structured_content, "meta")

        assert count == 3
        assert "<meta" in result
        assert result.count("<meta") == 3
        assert "<article" not in result

    def test_filter_multiple_tags(self, html_with_structured_content: str) -> None:
        """Test filtering with comma-separated selectors."""
        result, count = filter_html_by_selector(html_with_structured_content, "h1, p")

        assert count == 3  # 1 h1 + 2 p tags
        assert "<h1>" in result
        assert "<p>" in result
        assert "<meta" not in result

    def test_filter_by_class(self, html_with_structured_content: str) -> None:
        """Test filtering by class selector."""
        result, count = filter_html_by_selector(html_with_structured_content, ".main-content")

        assert count == 1
        assert "Article Title" in result
        assert "Footer content" not in result

    def test_filter_by_attribute(self, html_with_structured_content: str) -> None:
        """Test filtering by attribute selector."""
        result, count = filter_html_by_selector(
            html_with_structured_content, 'meta[property^="og:"]'
        )

        assert count == 2  # og:title and og:image
        assert 'property="og:title"' in result
        assert 'property="og:image"' in result
        assert 'name="description"' not in result

    def test_filter_descendant_combinator(self, html_with_structured_content: str) -> None:
        """Test filtering with descendant combinator."""
        result, count = filter_html_by_selector(html_with_structured_content, "article a")

        assert count == 1  # Only the link inside article
        assert 'href="/related"' in result
        assert 'href="/home"' not in result  # nav links excluded
        assert 'href="/about"' not in result

    def test_filter_multiple_elements(self, html_with_structured_content: str) -> None:
        """Test filtering that returns multiple elements."""
        result, count = filter_html_by_selector(html_with_structured_content, "img, video")

        assert count == 2
        assert "<img" in result
        assert "<video" in result

    def test_filter_nav_links(self, html_with_structured_content: str) -> None:
        """Test filtering links within navigation."""
        result, count = filter_html_by_selector(html_with_structured_content, "nav a")

        assert count == 2  # Home and About links
        assert 'href="/home"' in result
        assert 'href="/about"' in result
        assert 'href="/ad"' not in result  # sidebar link excluded

    def test_filter_no_matches(self, html_with_structured_content: str) -> None:
        """Test filtering with selector that matches nothing."""
        result, count = filter_html_by_selector(html_with_structured_content, ".nonexistent")

        assert count == 0
        assert result == ""

    def test_filter_invalid_selector(self, html_with_structured_content: str) -> None:
        """Test filtering with invalid CSS selector."""
        with pytest.raises(ValueError, match="Invalid CSS selector"):
            filter_html_by_selector(html_with_structured_content, "<<<invalid>>>")

    def test_filter_preserves_element_structure(
        self, html_with_structured_content: str
    ) -> None:
        """Test that filtered elements preserve their internal structure."""
        result, count = filter_html_by_selector(html_with_structured_content, "article")

        assert count == 1
        assert "<h1>Article Title</h1>" in result
        assert "<p>" in result
        assert "<img" in result
        assert "<video" in result

    def test_filter_empty_html(self) -> None:
        """Test filtering on empty HTML."""
        result, count = filter_html_by_selector("<html><body></body></html>", "div")

        assert count == 0
        assert result == ""

    def test_filter_complex_selector(self, html_with_structured_content: str) -> None:
        """Test filtering with complex CSS selector."""
        result, count = filter_html_by_selector(
            html_with_structured_content, "article.main-content p"
        )

        assert count == 1
        assert "Article paragraph" in result
        assert "Footer content" not in result
