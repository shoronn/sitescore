"""Fixed-window rate limits in Redis (or memory for development and tests)."""
from __future__ import annotations

import time

from redis import asyncio as aioredis


class RateLimiter:
    def __init__(self, redis_url: str | None):
        self._redis = aioredis.from_url(redis_url) if redis_url else None
        self._memory: dict[str, tuple[int, float]] = {}

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Count one hit; return True if still within `limit` for this window."""
        bucket = f"rl:{key}:{int(time.time() // window_seconds)}"
        if self._redis is not None:
            pipe = self._redis.pipeline()
            pipe.incr(bucket)
            pipe.expire(bucket, window_seconds + 5)
            count, _ = await pipe.execute()
            return int(count) <= limit
        count, expires = self._memory.get(bucket, (0, time.time() + window_seconds))
        self._memory[bucket] = (count + 1, expires)
        if len(self._memory) > 10_000:
            now = time.time()
            self._memory = {k: v for k, v in self._memory.items() if v[1] > now}
        return count + 1 <= limit

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
