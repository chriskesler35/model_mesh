"""Dependency injection."""

from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.redis import get_redis
from app.services.memory import MemoryManager
import redis.asyncio as redis


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_memory() -> MemoryManager:
    """Dependency to get memory manager."""
    redis_client = await get_redis()
    return MemoryManager(redis_client)