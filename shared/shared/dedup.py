"""Redis-backed URL deduplication.

Uses a Redis set of SHA256 hashes of normalized URLs to prevent
re-crawling the same page. For very large crawls (millions of URLs),
consider switching to a Redis Bloom filter.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import redis.asyncio as redis

# Session/tracking query params to strip during normalization
_STRIP_PARAMS = re.compile(
    r"^(jsessionid|phpsessid|sid|session_id|sessionid|cfid|cftoken|aspsessionid"
    r"|utm_source|utm_medium|utm_campaign|utm_term|utm_content"
    r"|fbclid|gclid|mc_cid|mc_eid|_ga|_gl)$",
    re.IGNORECASE,
)


class URLDedup:
    """Check and track seen URLs to prevent re-crawling."""

    CONTENT_HASH_KEY = "dedup:content_hashes"

    def __init__(
        self,
        redis_client: redis.Redis,
        key: str = "dedup:seen_urls",
    ) -> None:
        self.redis = redis_client
        self.key = key

    @staticmethod
    def normalize(url: str) -> str:
        """Normalize URL for dedup.

        - Lowercase
        - Strip fragments
        - Sort query params
        - Strip trailing slash (unless root)
        - Remove session/tracking query params
        - Normalize path (collapse //, resolve .. and .)
        - Strip default ports (:80 for http, :443 for https)
        """
        parsed = urlparse(url.strip().lower())

        # Strip default ports
        netloc = parsed.netloc
        if parsed.scheme == "http" and netloc.endswith(":80"):
            netloc = netloc[:-3]
        elif parsed.scheme == "https" and netloc.endswith(":443"):
            netloc = netloc[:-4]

        # Normalize path
        path = posixpath.normpath(parsed.path) if parsed.path else "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path

        # Filter out session/tracking params
        params = parse_qs(parsed.query)
        filtered_params = {
            k: v for k, v in params.items() if not _STRIP_PARAMS.match(k)
        }
        sorted_query = urlencode(sorted(filtered_params.items()), doseq=True)

        normalized = parsed._replace(
            netloc=netloc, path=path, fragment="", query=sorted_query,
        )
        return urlunparse(normalized)

    def _hash(self, url: str) -> str:
        return hashlib.sha256(self.normalize(url).encode()).hexdigest()

    async def is_seen(self, url: str) -> bool:
        """Check if URL has already been processed."""
        return bool(await self.redis.sismember(self.key, self._hash(url)))

    async def mark_seen(self, url: str) -> bool:
        """Mark URL as seen. Returns True if it was new, False if already seen."""
        result = await self.redis.sadd(self.key, self._hash(url))
        return result == 1

    async def mark_many(self, urls: list[str]) -> list[str]:
        """Mark multiple URLs as seen. Returns only the new (unseen) ones."""
        new_urls = []
        pipe = self.redis.pipeline()
        hashes = [(url, self._hash(url)) for url in urls]
        for _, h in hashes:
            pipe.sadd(self.key, h)
        results = await pipe.execute()
        for (url, _), added in zip(hashes, results):
            if added:
                new_urls.append(url)
        return new_urls

    async def count(self) -> int:
        """Number of unique URLs seen so far."""
        return await self.redis.scard(self.key)

    async def clear(self) -> None:
        """Reset the dedup set (e.g., for a fresh crawl)."""
        await self.redis.delete(self.key)

    # --- Content-based dedup ---

    async def is_content_seen(self, content_hash: str) -> bool:
        """Check if content with this hash has already been processed."""
        return bool(await self.redis.sismember(self.CONTENT_HASH_KEY, content_hash))

    async def mark_content_seen(self, content_hash: str) -> bool:
        """Mark content hash as seen. Returns True if new."""
        return await self.redis.sadd(self.CONTENT_HASH_KEY, content_hash) == 1

    # --- Per-domain URL ceiling ---

    async def domain_count(self, domain: str) -> int:
        """Number of URLs crawled for a domain."""
        return int(await self.redis.get(f"dedup:domain_count:{domain}") or 0)

    async def increment_domain(self, domain: str) -> int:
        """Increment and return the domain URL counter."""
        return await self.redis.incr(f"dedup:domain_count:{domain}")

    async def is_domain_exhausted(self, domain: str, max_urls: int) -> bool:
        """Check if a domain has hit its URL ceiling."""
        return await self.domain_count(domain) >= max_urls
