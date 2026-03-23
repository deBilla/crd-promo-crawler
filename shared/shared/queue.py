"""Redis-backed queue for inter-service communication.

Both the frontier queue and parsing queue use this abstraction.
Uses LPUSH/BRPOP for reliable FIFO ordering.
"""

from __future__ import annotations

import json
import logging
from typing import Type, TypeVar

import redis.asyncio as redis
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class RedisQueue:
    """A Redis-backed FIFO queue with Pydantic serialization.

    Messages are serialized to JSON via Pydantic's model_dump_json() on push
    and deserialized via model_validate_json() on pop. This ensures type safety
    across service boundaries.
    """

    def __init__(self, redis_client: redis.Redis, queue_name: str) -> None:
        self.redis = redis_client
        self.queue_name = f"queue:{queue_name}"

    async def push(self, item: BaseModel) -> None:
        """Add an item to the tail of the queue."""
        await self.redis.lpush(self.queue_name, item.model_dump_json())

    async def push_many(self, items: list[BaseModel]) -> None:
        """Add multiple items to the queue in a single pipeline call."""
        if not items:
            return
        pipe = self.redis.pipeline()
        for item in items:
            pipe.lpush(self.queue_name, item.model_dump_json())
        await pipe.execute()

    async def pop(self, model_class: Type[T], timeout: int = 0) -> T | None:
        """Pop an item from the head of the queue.

        Blocks for `timeout` seconds. 0 means block forever.
        Returns None if timeout expires without a message.
        """
        result = await self.redis.brpop(self.queue_name, timeout=timeout)
        if result is None:
            return None
        _, data = result
        return model_class.model_validate_json(data)

    async def pop_raw(self, timeout: int = 0) -> bytes | None:
        """Pop raw bytes — use when you need custom error handling on deserialization."""
        result = await self.redis.brpop(self.queue_name, timeout=timeout)
        if result is None:
            return None
        _, data = result
        return data

    async def push_raw(self, data: bytes) -> None:
        """Push raw bytes back to the queue (e.g., for retry)."""
        await self.redis.lpush(self.queue_name, data)

    async def size(self) -> int:
        """Number of items currently in the queue."""
        return await self.redis.llen(self.queue_name)

    async def clear(self) -> None:
        """Remove all items from the queue."""
        await self.redis.delete(self.queue_name)

    async def peek(self, model_class: Type[T], count: int = 10) -> list[T]:
        """View items without removing them (for debugging)."""
        raw_items = await self.redis.lrange(self.queue_name, -count, -1)
        items = []
        for raw in raw_items:
            try:
                items.append(model_class.model_validate_json(raw))
            except ValidationError:
                continue
        return items
