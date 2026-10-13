"""
High-Concurrency Cache-Aside Pattern Implementation
Powered by redis.asyncio with Connection Pooling & Resilient Failover
"""

import json
import logging
from typing import Any, Optional
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from async_api.config import settings

logger = logging.getLogger("async_api.cache")


class RedisCacheManager:
    """
    Manages asynchronous Redis connection pool and Cache-Aside operations.
    Enforces sub-2ms cache reads and graceful degradation during cache outages.
    """

    def __init__(self) -> None:
        self.pool: Optional[aioredis.ConnectionPool] = None
        self.client: Optional[aioredis.Redis] = None
        self._is_connected: bool = False

    async def init_pool(self) -> None:
        """Initializes the Redis async connection pool during app startup."""
        if not settings.CACHE_ENABLED:
            logger.info("Caching is disabled via configuration.")
            return

        try:
            self.pool = aioredis.ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_POOL_SIZE,
                socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
                socket_connect_timeout=settings.REDIS_TIMEOUT_SECONDS,
                decode_responses=True,
            )
            self.client = aioredis.Redis(connection_pool=self.pool)
            # Verify connectivity
            await self.client.ping()
            self._is_connected = True
            logger.info(f"✅ Redis Async Connection Pool initialized at {settings.REDIS_URL} (max_connections={settings.REDIS_POOL_SIZE})")
        except Exception as e:
            self._is_connected = False
            logger.warning(f"⚠️ Redis unavailable at startup ({e}). Falling back to pure async database mode gracefully.")

    async def close(self) -> None:
        """Gracefully closes Redis connection pool on app shutdown."""
        if self.client:
            await self.client.aclose()
        if self.pool:
            await self.pool.disconnect()
        self._is_connected = False
        logger.info("Redis cache pool closed.")

    async def get(self, key: str) -> Optional[Any]:
        """
        Asynchronously fetches cached data from Redis.
        Target SLA: <2ms latency.
        Returns None on cache miss or Redis failure.
        """
        if not self._is_connected or not self.client:
            return None

        try:
            val = await self.client.get(key)
            if val is not None:
                return json.loads(val)
            return None
        except RedisError as re:
            logger.warning(f"Redis read error on key '{key}': {re}. Degrading to database query.")
            return None
        except Exception as e:
            logger.error(f"Unexpected deserialization error for key '{key}': {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Asynchronously stores data in Redis with a 5-minute default TTL (300 seconds).
        Non-blocking, fails gracefully.
        """
        if not self._is_connected or not self.client:
            return False

        expiry = ttl if ttl is not None else settings.CACHE_TTL_SECONDS
        try:
            serialized = json.dumps(value, default=str)
            await self.client.set(key, serialized, ex=expiry)
            return True
        except RedisError as re:
            logger.warning(f"Redis write error on key '{key}': {re}")
            return False

    async def delete(self, key: str) -> bool:
        """Invalidates a cache key upon entity modification (Cache-Aside pattern)."""
        if not self._is_connected or not self.client:
            return False

        try:
            await self.client.delete(key)
            return True
        except RedisError as re:
            logger.warning(f"Redis delete error on key '{key}': {re}")
            return False

    async def ping(self) -> bool:
        """Liveness check for health probe."""
        if not self._is_connected or not self.client:
            return False
        try:
            return bool(await self.client.ping())
        except Exception:
            return False


# Global Cache Manager Singleton
cache_manager = RedisCacheManager()
