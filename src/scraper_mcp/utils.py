"""Utility functions for HTML processing."""

from __future__ import annotations

from bs4 import BeautifulSoup
from markdownify import markdownify


def html_to_markdown(html: str, strip_tags: list[str] | None = None) -> str:
    """Convert HTML to markdown format.

    Args:
        html: The HTML content to convert
        strip_tags: List of HTML tags to strip (e.g., ['script', 'style'])

    Returns:
        Markdown formatted text
    """
    # Parse HTML
    soup = BeautifulSoup(html, "lxml")

    # Strip unwanted tags
    if strip_tags:
        for tag in strip_tags:
            for element in soup.find_all(tag):
                element.decompose()

    # Convert to markdown
    markdown = markdownify(str(soup), heading_style="ATX")
    return markdown.strip()


def html_to_text(html: str, strip_tags: list[str] | None = None) -> str:
    """Extract plain text from HTML.

    Args:
        html: The HTML content to process
        strip_tags: List of HTML tags to strip (e.g., ['script', 'style'])

    Returns:
        Plain text content
    """
    # Parse HTML
    soup = BeautifulSoup(html, "lxml")

    # Strip unwanted tags
    default_strip_tags = ["script", "style", "meta", "link", "noscript"]
    tags_to_strip = strip_tags if strip_tags is not None else default_strip_tags

    for tag in tags_to_strip:
        for element in soup.find_all(tag):
            element.decompose()

    # Extract text
    text = soup.get_text(separator="\n", strip=True)

    # Clean up multiple newlines
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


def extract_links(html: str, base_url: str | None = None) -> list[dict[str, str]]:
    """Extract all links from HTML.

    Args:
        html: The HTML content to process
        base_url: Optional base URL for resolving relative links

    Returns:
        List of dictionaries containing link information
    """
    from urllib.parse import urljoin

    soup = BeautifulSoup(html, "lxml")
    links = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.get_text(strip=True)

        # Resolve relative URLs if base_url provided
        if base_url:
            href = urljoin(base_url, href)

        links.append({"url": href, "text": text, "title": link.get("title", "")})

    return links


def extract_metadata(html: str) -> dict[str, str]:
    """Extract metadata from HTML (title, description, etc.).

    Args:
        html: The HTML content to process

    Returns:
        Dictionary containing metadata
    """
    soup = BeautifulSoup(html, "lxml")
    metadata: dict[str, str] = {}

    # Extract title
    if soup.title:
        metadata["title"] = soup.title.string or ""

    # Extract meta tags
    for meta in soup.find_all("meta"):
        name = meta.get("name") or meta.get("property")
        content = meta.get("content")

        if name and content:
            metadata[name] = content

    return metadata
