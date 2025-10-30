"""Pytest configuration and fixtures for scraper-mcp tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_html() -> str:
    """Sample HTML for testing."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="description" content="A sample page for testing">
        <meta property="og:title" content="Sample Page">
        <title>Test Page Title</title>
        <script>console.log('should be stripped');</script>
        <style>.test { color: red; }</style>
    </head>
    <body>
        <h1>Main Heading</h1>
        <p>This is a <strong>sample</strong> paragraph with <em>formatting</em>.</p>
        <h2>Subheading</h2>
        <ul>
            <li><a href="https://example.com">Example Link</a></li>
            <li><a href="/relative" title="Relative Link">Relative</a></li>
            <li><a href="#anchor">Anchor Link</a></li>
        </ul>
        <div>
            <p>Another paragraph with some text.</p>
        </div>
        <noscript>No JavaScript content</noscript>
    </body>
    </html>
    """


@pytest.fixture
def simple_html() -> str:
    """Simple HTML for basic testing."""
    return """
    <html>
    <head><title>Simple Page</title></head>
    <body>
        <h1>Hello World</h1>
        <p>This is a simple test.</p>
    </body>
    </html>
    """


@pytest.fixture
def html_with_links() -> str:
    """HTML with various types of links."""
    return """
    <html>
    <body>
        <a href="https://example.com">External Link</a>
        <a href="https://example.com/page" title="Page Title">External with Title</a>
        <a href="/relative/path">Relative Link</a>
        <a href="#section">Anchor Link</a>
        <a href="mailto:test@example.com">Email Link</a>
        <a>Link without href</a>
    </body>
    </html>
    """


@pytest.fixture
def html_with_metadata() -> str:
    """HTML with various metadata tags."""
    return """
    <html>
    <head>
        <title>Metadata Test Page</title>
        <meta name="description" content="Test description">
        <meta name="keywords" content="test, metadata, html">
        <meta property="og:title" content="OG Title">
        <meta property="og:description" content="OG Description">
        <meta property="og:image" content="https://example.com/image.jpg">
        <meta name="twitter:card" content="summary">
    </head>
    <body>
        <h1>Content</h1>
    </body>
    </html>
    """
