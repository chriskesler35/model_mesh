"""Health check endpoints."""

from fastapi import APIRouter
from sqlalchemy import text
from app.database import engine
from app.redis import get_redis
import redis.asyncio as redis

router = APIRouter(tags=["health"])


@router.get("/v1/health")
@router.get("/health")
async def health_check():
    """Health check endpoint."""
    checks = {
        "status": "healthy",
        "database": "unknown",
        "redis": "unknown"
    }
    
    # Check database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "unhealthy"
        checks["status"] = "degraded"
    
    # Check Redis — optional, only degrades status if a URL is configured but unreachable
    from app.config import settings
    try:
        redis_client = await get_redis()
        if redis_client is None:
            checks["redis"] = "not configured (optional)"
        else:
            await redis_client.ping()
            checks["redis"] = "healthy"
    except Exception:
        if settings.redis_url:
            # Explicitly configured but unreachable — that's a real problem
            checks["redis"] = "unhealthy"
            checks["status"] = "degraded"
        else:
            checks["redis"] = "not configured (optional)"

    return checks