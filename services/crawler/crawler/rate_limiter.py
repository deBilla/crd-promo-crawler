"""Per-domain rate limiter using Redis.

Ensures we don't hammer any single domain with too many requests.
Uses a simple timestamp-based approach per domain.
"""

from __future__ import annotations

import asyncio
import time

import redis.asyncio as redis


class DomainRateLimiter:
    """Rate limit requests per domain using Redis timestamps."""

    def __init__(self, redis_client: redis.Redis, delay: float = 1.0) -> None:
        self.redis = redis_client
        self.delay = delay
        self._prefix = "ratelimit"

    async def acquire(self, domain: str) -> None:
        """Wait until it's safe to make a request to this domain.

        Checks the last request time and sleeps if needed to maintain
        the configured delay between requests to the same domain.
        """
        key = f"{self._prefix}:{domain}"
        now = time.monotonic()

        last_request = await self.redis.get(key)
        if last_request is not None:
            elapsed = now - float(last_request)
            remaining = self.delay - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)

        await self.redis.set(key, str(time.monotonic()), ex=int(self.delay * 10))
