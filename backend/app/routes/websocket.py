"""WebSocket endpoint for real-time collaboration."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.services.ws_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
):
    """
    WebSocket endpoint for real-time updates.

    Connect with: ws://host/ws?token=<jwt_token>

    Message types (client -> server):
      - subscribe:   { "type": "subscribe",   "channel": "conversation:<uuid>" }
      - unsubscribe: { "type": "unsubscribe", "channel": "conversation:<uuid>" }
      - ping:        { "type": "ping" }

    Message types (server -> client):
      - connected:    sent on successful auth, includes online_users list
      - subscribed:   confirms channel subscription
      - unsubscribed: confirms channel unsubscription
      - ping:         server heartbeat (client should reply with { "type": "pong" })
      - pong:         reply to client ping

    All server messages wrapped in: { "type": str, "payload": obj, "timestamp": str }
    """
    # Authenticate via JWT token or master API key
    user = await _authenticate_ws(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid or missing token")
        return

    user_id = str(user.get("id", user.get("sub", "anonymous")))
    await manager.connect(websocket, user_id)

    # Start heartbeat task
    heartbeat_task = asyncio.create_task(_heartbeat(websocket, user_id))

    try:
        # Send welcome message
        await manager.send_to_user(user_id, {
            "type": "connected",
            "payload": {
                "user_id": user_id,
                "online_users": manager.get_online_users(),
            },
        })

        # Main message loop
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = message.get("type", "")

            if msg_type == "ping":
                # Client-initiated ping — reset missed counter and reply
                manager._missed_pings[id(websocket)] = 0
                await websocket.send_text(json.dumps({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))

            elif msg_type == "pong":
                # Client responding to server heartbeat ping — reset missed counter
                manager._missed_pings[id(websocket)] = 0

            elif msg_type == "subscribe":
                channel = message.get("channel", "")
                if channel:
                    manager.subscribe(user_id, channel)
                    await manager.send_to_user(user_id, {
                        "type": "subscribed",
                        "payload": {"channel": channel},
                    })

            elif msg_type == "unsubscribe":
                channel = message.get("channel", "")
                if channel:
                    manager.unsubscribe(user_id, channel)
                    await manager.send_to_user(user_id, {
                        "type": "unsubscribed",
                        "payload": {"channel": channel},
                    })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for user={user_id}: {e}")
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        manager.disconnect(websocket)


async def _authenticate_ws(token: str) -> dict | None:
    """Authenticate WebSocket connection via JWT token or master API key.

    Uses the same decode_jwt / get_user_by_id functions as the REST auth
    middleware, keeping auth logic consistent across transports.
    """
    if not token:
        return None

    # Try JWT first
    try:
        from app.routes.collaboration import decode_jwt, get_user_by_id
        payload = decode_jwt(token)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                user = get_user_by_id(user_id)
                if user and user.get("is_active", True):
                    return user
    except Exception as e:
        logger.debug(f"JWT auth failed for WebSocket: {e}")

    # Fall back to master API key
    try:
        from app.config import settings
        if token == settings.modelmesh_api_key:
            return {
                "id": "owner",
                "username": "owner",
                "display_name": "Owner",
                "role": "owner",
            }
    except Exception:
        pass

    return None


async def _heartbeat(websocket: WebSocket, user_id: str):
    """Send ping every 30s. Disconnect after 3 missed pongs.

    The server sends {"type": "ping"} and increments missed count.
    When the client replies with {"type": "pong"}, the message loop
    resets the missed count to 0.  If 3 consecutive pings go
    unanswered, the connection is closed with code 4002.
    """
    try:
        while True:
            await asyncio.sleep(30)
            ws_id = id(websocket)
            missed = manager._missed_pings.get(ws_id, 0)
            if missed >= 3:
                logger.warning(f"Heartbeat timeout for user={user_id} (3 missed pings), closing")
                try:
                    await websocket.close(code=4002, reason="Heartbeat timeout")
                except Exception:
                    pass
                break
            manager._missed_pings[ws_id] = missed + 1
            try:
                await websocket.send_text(json.dumps({
                    "type": "ping",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
            except Exception:
                break
    except asyncio.CancelledError:
        raise
