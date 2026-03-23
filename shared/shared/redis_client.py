"""Redis connection factory."""

from __future__ import annotations

import redis.asyncio as redis


async def create_redis(url: str = "redis://localhost:6379/0") -> redis.Redis:
    """Create an async Redis client.

    The caller is responsible for calling `await client.aclose()` on shutdown.
    """
    return redis.from_url(url, decode_responses=False)
