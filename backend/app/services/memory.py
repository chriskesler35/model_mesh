"""Memory management with Redis backing and graceful degradation."""

import json
import uuid
import logging
from typing import Optional
import redis.asyncio as redis
from app.config import settings

logger = logging.getLogger(__name__)


class RedisUnavailableError(Exception):
    """Raised when Redis is unavailable but required."""
    pass


class MemoryManager:
    """Redis-backed conversation memory with graceful degradation."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.default_ttl = settings.memory_ttl_seconds
        self.enabled = True
    
    async def health_check(self) -> bool:
        """Check if Redis is available."""
        try:
            await self.redis.ping()
            self.enabled = True
            return True
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            self.enabled = False
            return False
    
    async def get_context(
        self, conversation_id: str, new_messages: list, max_messages: int
    ) -> list:
        """Retrieve recent message history and append new messages."""
        if not self.enabled:
            return new_messages  # Graceful degradation
        
        key = f"conversation:{conversation_id}:messages"
        # Get last N messages (FIFO - oldest first)
        try:
            history = await self.redis.lrange(key, -max_messages, -1)
            history = [json.loads(m) for m in history]
            return history + new_messages
        except Exception as e:
            logger.error(f"Failed to get context: {e}")
            return new_messages
    
    async def store_messages(
        self, conversation_id: str, messages: list, max_messages: int = None
    ) -> None:
        """Persist messages to conversation history with configurable limit."""
        if not self.enabled:
            return  # Graceful degradation: skip storing
        
        key = f"conversation:{conversation_id}:messages"
        try:
            for msg in messages:
                await self.redis.rpush(key, json.dumps(msg))
            
            # Enforce max_messages limit (trim old messages)
            limit = max_messages or settings.default_max_memory_messages
            await self.redis.ltrim(key, -limit, -1)
            
            # Set/configure TTL
            await self.redis.expire(key, self.default_ttl)
        except Exception as e:
            logger.error(f"Failed to store messages: {e}")
    
    async def clear_conversation(self, conversation_id: str) -> None:
        """Clear conversation memory."""
        if not self.enabled:
            return
        
        try:
            await self.redis.delete(f"conversation:{conversation_id}:messages")
        except Exception as e:
            logger.error(f"Failed to clear conversation: {e}")
    
    async def create_conversation_id(self) -> str:
        """Generate a new conversation ID if client doesn't provide one."""
        return str(uuid.uuid4())