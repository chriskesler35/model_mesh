"""Redis connection management."""

import redis.asyncio as redis
from app.config import settings

redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get Redis client, creating if needed."""
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return redis_client


async def close_redis():
    """Close Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None