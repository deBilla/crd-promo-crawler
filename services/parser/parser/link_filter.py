"""URL filtering logic for crawler frontier."""

import re
from urllib.parse import urlparse


# Patterns to exclude from crawling
EXCLUDE_PATTERNS = [
    r"/careers?(/|$)",
    r"/jobs?(/|$)",
    r"/login(/|$)",
    r"/logout(/|$)",
    r"/signin(/|$)",
    r"/signout(/|$)",
    r"/register(/|$)",
    r"/sign-up(/|$)",
    r"/investor.*",
    r"/investors(/|$)",
    r"/annual-report.*",
    r"/press(/|$)",
    r"/terms(/|$)",
    r"/privacy(/|$)",
    r"/contact.*",
    r"/support(/|$)",
    r"/help(/|$)",
    r"/feedback(/|$)",
    r"/download.*",
    r"/pdf(/|$)",
    r"/document.*",
]

# Compiled regex patterns
COMPILED_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in EXCLUDE_PATTERNS]


MAX_URL_LENGTH = 2048
MAX_PATH_SEGMENTS = 10


def filter_urls(
    urls: list[str],
    domain: str,
    max_depth: int,
    current_depth: int,
    bank_url_patterns: list[re.Pattern] | None = None,
) -> list[str]:
    """Filter URLs based on domain, depth, and pattern matching.

    Keeps only URLs that:
    - Are on the same domain as the source
    - Don't exceed max_depth
    - Don't match exclude patterns
    - Don't exceed URL length or path depth limits (trap prevention)
    - Match bank-specific URL patterns (if provided)

    Args:
        urls: List of URLs to filter.
        domain: Source domain (e.g., 'example.com').
        max_depth: Maximum depth allowed.
        current_depth: Current depth in the crawl tree.
        bank_url_patterns: Optional compiled regexes from bank config url_patterns.

    Returns:
        Filtered list of URLs that pass all checks.
    """
    filtered = []
    next_depth = current_depth + 1

    if next_depth > max_depth:
        return []

    for url in urls:
        # Trap prevention: URL length limit
        if len(url) > MAX_URL_LENGTH:
            continue

        # Parse URL
        parsed = urlparse(url)
        url_domain = parsed.netloc.lower()

        # Trap prevention: path segment depth limit
        if parsed.path.count("/") > MAX_PATH_SEGMENTS:
            continue

        # Check if same domain (remove www. prefix for comparison)
        url_domain_clean = url_domain.replace("www.", "").replace("www2.", "")
        domain_clean = domain.replace("www.", "").replace("www2.", "")

        if url_domain_clean != domain_clean:
            continue

        # Check against exclude patterns
        path = parsed.path.lower()
        if any(pattern.search(path) for pattern in COMPILED_PATTERNS):
            continue

        # Bank-specific URL pattern whitelist
        if bank_url_patterns:
            if not any(p.match(url) for p in bank_url_patterns):
                continue

        filtered.append(url)

    return filtered
