"""
WebSocket connection manager for real-time collaboration.

Tracks connected clients, handles subscriptions, broadcasts messages,
and maintains user presence/activity state.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections, subscriptions, broadcasting, and presence."""

    def __init__(self):
        # user_id -> list of WebSocket connections (user can have multiple tabs)
        self.active_connections: dict[str, list[WebSocket]] = {}
        # channel -> set of user_ids subscribed
        self.channels: dict[str, set[str]] = {}
        # websocket id -> user_id reverse lookup
        self._ws_to_user: dict[int, str] = {}
        # websocket id -> missed pings count
        self._missed_pings: dict[int, int] = {}
        # user_id -> presence info {page, activity, last_seen, username, display_name}
        self.presence: dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept connection and register user."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        self._ws_to_user[id(websocket)] = user_id
        self._missed_pings[id(websocket)] = 0
        logger.info(f"WebSocket connected: user={user_id}, total={self.total_connections}")

    def disconnect(self, websocket: WebSocket):
        """Remove connection and clean up subscriptions + presence."""
        ws_id = id(websocket)
        user_id = self._ws_to_user.pop(ws_id, None)
        self._missed_pings.pop(ws_id, None)
        if user_id and user_id in self.active_connections:
            self.active_connections[user_id] = [
                ws for ws in self.active_connections[user_id] if id(ws) != ws_id
            ]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                # Remove user from all channels when last connection closes
                for channel_users in self.channels.values():
                    channel_users.discard(user_id)
                # Clean up empty channels
                self.channels = {
                    ch: users for ch, users in self.channels.items() if users
                }
                # Clean up presence when user fully disconnects
                self.presence.pop(user_id, None)
        logger.info(f"WebSocket disconnected: user={user_id}, total={self.total_connections}")
        return user_id

    def subscribe(self, user_id: str, channel: str):
        """Subscribe user to a channel."""
        if channel not in self.channels:
            self.channels[channel] = set()
        self.channels[channel].add(user_id)
        logger.debug(f"User {user_id} subscribed to channel {channel}")

    def unsubscribe(self, user_id: str, channel: str):
        """Unsubscribe user from a channel."""
        if channel in self.channels:
            self.channels[channel].discard(user_id)
            if not self.channels[channel]:
                del self.channels[channel]
        logger.debug(f"User {user_id} unsubscribed from channel {channel}")

    # ─── Presence tracking ───────────────────────────────────────────────────

    def update_presence(
        self,
        user_id: str,
        page: str = "",
        activity: str = "",
        username: str = "",
        display_name: str = "",
    ):
        """Update user's presence info (page, activity, last_seen)."""
        existing = self.presence.get(user_id, {})
        self.presence[user_id] = {
            "page": page or existing.get("page", ""),
            "activity": activity or existing.get("activity", ""),
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "username": username or existing.get("username", user_id),
            "display_name": display_name or existing.get("display_name", ""),
        }

    def get_presence(self) -> list[dict]:
        """Return all online users with their presence info, filtering stale entries."""
        now = datetime.now(timezone.utc)
        online: list[dict] = []
        for user_id in list(self.active_connections.keys()):
            info = self.presence.get(user_id, {})
            last_seen = info.get("last_seen", "")
            # Check TTL - 2 minutes (120 seconds)
            if last_seen:
                try:
                    seen = datetime.fromisoformat(last_seen)
                    if (now - seen).total_seconds() > 120:
                        continue  # stale — user has active WS but no heartbeat
                except (ValueError, TypeError):
                    pass
            online.append({
                "user_id": user_id,
                "username": info.get("username", user_id),
                "display_name": info.get("display_name", ""),
                "page": info.get("page", ""),
                "activity": info.get("activity", ""),
                "last_seen": last_seen,
            })
        return online

    # ─── Messaging ───────────────────────────────────────────────────────────

    async def send_to_user(self, user_id: str, message: dict):
        """Send message to all connections of a specific user."""
        msg = self._wrap_message(message)
        connections = self.active_connections.get(user_id, [])
        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        # Clean up any dead connections discovered during send
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_to_channel(
        self, channel: str, message: dict, exclude_user: Optional[str] = None
    ):
        """Broadcast message to all users subscribed to a channel."""
        user_ids = self.channels.get(channel, set()).copy()
        msg = self._wrap_message(message)
        for user_id in user_ids:
            if user_id == exclude_user:
                continue
            connections = self.active_connections.get(user_id, [])
            for ws in connections:
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass

    async def broadcast_all(self, message: dict):
        """Broadcast message to all connected users."""
        msg = self._wrap_message(message)
        for connections in self.active_connections.values():
            for ws in connections:
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass

    def get_online_users(self) -> list[str]:
        """Return list of connected user IDs."""
        return list(self.active_connections.keys())

    def get_channel_users(self, channel: str) -> list[str]:
        """Return list of user IDs subscribed to a channel."""
        return list(self.channels.get(channel, set()))

    @property
    def total_connections(self) -> int:
        """Total number of active WebSocket connections across all users."""
        return sum(len(conns) for conns in self.active_connections.values())

    def _wrap_message(self, message: dict) -> str:
        """Wrap message with standard format: { type, payload, timestamp }."""
        wrapped = {
            "type": message.get("type", "message"),
            "payload": message.get("payload", message),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return json.dumps(wrapped)


# Singleton instance — import this from other modules
manager = ConnectionManager()
