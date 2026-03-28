"""Rate limiting middleware with Redis backing."""

import time
import logging
from fastapi import Request, HTTPException
from app.config import settings
from app.redis import get_redis

logger = logging.getLogger(__name__)


class RateLimiter:
    """Redis-backed sliding window rate limiter."""

    def __init__(self, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        self.enabled = True

    async def _get_redis(self):
        """Get Redis client lazily."""
        try:
            redis = await get_redis()
            return redis
        except Exception as e:
            logger.warning(f"Redis unavailable for rate limiting: {e}")
            self.enabled = False
            return None

    async def check_rate_limit(self, api_key: str) -> tuple[bool, dict]:
        """
        Check if request is within rate limits.
        Returns (allowed: bool, headers: dict).
        """
        if not self.enabled:
            return True, {}

        redis = await self._get_redis()
        if not redis:
            # Graceful degradation: allow if Redis unavailable
            return True, {}

        try:
            now = time.time()
            minute_key = f"ratelimit:{api_key}:minute"
            hour_key = f"ratelimit:{api_key}:hour"

            # Check minute limit
            minute_count = await redis.get(minute_key)
            minute_count = int(minute_count) if minute_count else 0

            if minute_count >= self.rpm:
                ttl = await redis.ttl(minute_key)
                return False, {
                    "X-RateLimit-Limit": str(self.rpm),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + ttl)),
                    "Retry-After": str(ttl)
                }

            # Check hour limit
            hour_count = await redis.get(hour_key)
            hour_count = int(hour_count) if hour_count else 0

            if hour_count >= self.rph:
                ttl = await redis.ttl(hour_key)
                return False, {
                    "X-RateLimit-Limit": str(self.rph),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + ttl)),
                    "Retry-After": str(ttl)
                }

            # Increment counters
            pipe = redis.pipeline()

            # Minute counter (expires in 60 seconds)
            pipe.incr(minute_key)
            pipe.expire(minute_key, 60)

            # Hour counter (expires in 3600 seconds)
            pipe.incr(hour_key)
            pipe.expire(hour_key, 3600)

            await pipe.execute()

            # Calculate remaining
            remaining_minute = self.rpm - minute_count - 1
            remaining_hour = self.rph - hour_count - 1

            return True, {
                "X-RateLimit-Limit": str(self.rpm),
                "X-RateLimit-Remaining": str(min(remaining_minute, remaining_hour)),
                "X-RateLimit-Reset": str(int(now + 60))
            }

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Allow on error (fail open)
            return True, {}

    async def reset_limits(self, api_key: str) -> None:
        """Reset rate limits for an API key (admin function)."""
        redis = await self._get_redis()
        if redis:
            await redis.delete(f"ratelimit:{api_key}:minute")
            await redis.delete(f"ratelimit:{api_key}:hour")


# Default rate limiter instance
rate_limiter = RateLimiter(
    requests_per_minute=getattr(settings, 'rate_limit_rpm', 60),
    requests_per_hour=getattr(settings, 'rate_limit_rph', 1000)
)


async def check_rate_limit(request: Request) -> None:
    """
    Dependency to check rate limits.
    Raises HTTPException if rate limit exceeded.
    """
    # Skip rate limiting in development
    if settings.modelmesh_api_key == "modelmesh_local_dev_key":
        return

    # Get API key from request state (set by auth middleware)
    api_key = getattr(request.state, 'api_key', None)
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={"error": {"type": "authentication_error", "message": "No API key provided", "code": "missing_api_key"}}
        )

    allowed, headers = await rate_limiter.check_rate_limit(api_key)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "type": "rate_limit_error",
                    "message": "Rate limit exceeded. Please retry after the specified time.",
                    "code": "rate_limit_exceeded"
                }
            },
            headers=headers
        )

    # Store headers for response
    request.state.rate_limit_headers = headers