"""Session management using Redis for tracking active user sessions.

Each login creates a session record in Redis, keyed by user_id + session_id.
A session index (Redis set) tracks all session IDs per user for efficient listing.
Sessions auto-expire with the same TTL as JWT tokens.
"""

import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages user sessions in Redis.

    Key schema:
        session:{user_id}:{session_id}  -> JSON session data (string, TTL = jwt_expiry)
        sessions:{user_id}              -> Redis SET of session_id strings (TTL refreshed)
    """

    def __init__(self, redis_client, expiry_hours: int = 24 * 7):
        self.redis = redis_client
        self.expiry = timedelta(hours=expiry_hours)

    async def create_session(
        self,
        user_id: str,
        user_agent: str = "",
        ip_address: str = "",
    ) -> str:
        """Create a new session. Returns session_id."""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "user_agent": user_agent,
            "ip_address": ip_address,
            "created_at": now,
            "last_active": now,
        }

        ttl = int(self.expiry.total_seconds())
        key = f"session:{user_id}:{session_id}"
        await self.redis.set(key, json.dumps(session_data), ex=ttl)

        # Add to user's session index set
        index_key = f"sessions:{user_id}"
        await self.redis.sadd(index_key, session_id)
        await self.redis.expire(index_key, ttl)

        logger.info("Session created for user %s: %s", user_id, session_id)
        return session_id

    async def get_sessions(self, user_id: str) -> list[dict]:
        """Get all active sessions for a user."""
        index_key = f"sessions:{user_id}"
        session_ids = await self.redis.smembers(index_key)

        sessions = []
        for sid in session_ids:
            # decode_responses=True means sid is already str
            sid_str = sid if isinstance(sid, str) else sid.decode()
            key = f"session:{user_id}:{sid_str}"
            data = await self.redis.get(key)
            if data:
                raw = data if isinstance(data, str) else data.decode()
                sessions.append(json.loads(raw))
            else:
                # Session key expired but index entry remains -- clean up
                await self.redis.srem(index_key, sid)

        return sorted(sessions, key=lambda s: s.get("last_active", ""), reverse=True)

    async def revoke_session(self, user_id: str, session_id: str) -> bool:
        """Revoke (delete) a specific session. Returns True if it existed."""
        key = f"session:{user_id}:{session_id}"
        deleted = await self.redis.delete(key)
        await self.redis.srem(f"sessions:{user_id}", session_id)
        if deleted:
            logger.info("Session revoked for user %s: %s", user_id, session_id)
        return deleted > 0

    async def revoke_all_except(self, user_id: str, keep_session_id: str) -> int:
        """Revoke all sessions for a user except the specified one.

        Returns the number of sessions revoked.
        """
        index_key = f"sessions:{user_id}"
        session_ids = await self.redis.smembers(index_key)

        count = 0
        for sid in session_ids:
            sid_str = sid if isinstance(sid, str) else sid.decode()
            if sid_str != keep_session_id:
                await self.redis.delete(f"session:{user_id}:{sid_str}")
                await self.redis.srem(index_key, sid)
                count += 1

        logger.info(
            "Revoked %d sessions for user %s (kept %s)", count, user_id, keep_session_id
        )
        return count

    async def touch_session(self, user_id: str, session_id: str) -> None:
        """Update last_active timestamp and refresh TTL."""
        key = f"session:{user_id}:{session_id}"
        data = await self.redis.get(key)
        if data:
            raw = data if isinstance(data, str) else data.decode()
            session = json.loads(raw)
            session["last_active"] = datetime.now(timezone.utc).isoformat()
            ttl = int(self.expiry.total_seconds())
            await self.redis.set(key, json.dumps(session), ex=ttl)

    async def validate_session(self, user_id: str, session_id: str) -> bool:
        """Check if a session is still valid (exists in Redis)."""
        key = f"session:{user_id}:{session_id}"
        return await self.redis.exists(key) > 0
