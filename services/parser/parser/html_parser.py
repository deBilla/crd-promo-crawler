"""HTML parsing utilities for extracting text, title, and links."""

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def extract_text(html: bytes) -> str:
    """Extract visible text from HTML content.

    Args:
        html: HTML content as bytes.

    Returns:
        Extracted visible text with normalized whitespace.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove script and style tags
    for tag in soup(["script", "style"]):
        tag.decompose()

    # Get text
    text = soup.get_text()

    # Normalize whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = " ".join(chunk for chunk in chunks if chunk)

    return text


def extract_title(html: bytes) -> str:
    """Extract page title from HTML content.

    Args:
        html: HTML content as bytes.

    Returns:
        Page title, or empty string if not found.
    """
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)

    return ""


def extract_links(html: bytes, base_url: str) -> list[str]:
    """Extract all href links from HTML content and resolve relative URLs.

    Filters out non-HTTP schemes (mailto, javascript, tel, etc.) and
    deduplicates URLs.

    Args:
        html: HTML content as bytes.
        base_url: Base URL for resolving relative links.

    Returns:
        List of unique, absolute HTTP(S) URLs.
    """
    soup = BeautifulSoup(html, "lxml")

    links = set()
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href:
            continue

        # Resolve relative URLs
        absolute_url = urljoin(base_url, href)

        # Filter out non-HTTP schemes
        parsed = urlparse(absolute_url)
        if parsed.scheme not in ("http", "https"):
            continue

        # Remove fragments and add to set
        url_without_fragment = absolute_url.split("#")[0]
        links.add(url_without_fragment)

    return sorted(list(links))
