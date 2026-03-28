"""Telegram bot integration for remote DevForgeAI access."""

import httpx
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import os
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/telegram", tags=["telegram"])

# Telegram Bot Token (set in environment)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None

# Authorized chat IDs (set in environment, comma-separated)
AUTHORIZED_CHAT_IDS = [
    int(cid) for cid in (os.environ.get("TELEGRAM_CHAT_IDS", "").split(",") if os.environ.get("TELEGRAM_CHAT_IDS") else [])
]


class TelegramMessage(BaseModel):
    """Telegram message webhook."""
    update_id: int
    message: Optional[Dict[str, Any]] = None


class SendMessage(BaseModel):
    """Send a message."""
    chat_id: str
    text: str
    parse_mode: Optional[str] = "Markdown"


def is_authorized(chat_id: int) -> bool:
    """Check if chat ID is authorized."""
    if not AUTHORIZED_CHAT_IDS:
        return True  # Allow all if not configured
    return chat_id in AUTHORIZED_CHAT_IDS


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """Handle incoming Telegram webhook."""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")
    
    try:
        body = await request.json()
        logger.info(f"Telegram webhook received: {json.dumps(body, indent=2)[:500]}")
    except Exception as e:
        logger.error(f"Failed to parse webhook body: {e}")
        raise HTTPException(status_code=400, detail="Invalid request body")
    
    # Extract message
    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"status": "ok", "message": "No message in update"}
    
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    
    if not chat_id or not text:
        return {"status": "ok", "message": "No chat_id or text"}
    
    # Check authorization
    if not is_authorized(chat_id):
        await send_telegram_message(chat_id, "⚠️ Unauthorized access")
        return {"status": "unauthorized"}
    
    # Process command in background
    background_tasks.add_task(process_telegram_command, chat_id, text)
    
    return {"status": "ok"}


@router.post("/send")
async def send_message(msg: SendMessage):
    """Send a message to a Telegram chat."""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")
    
    return await send_telegram_message(msg.chat_id, msg.text, msg.parse_mode)


@router.get("/status")
async def telegram_status():
    """Get Telegram bot status."""
    if not TELEGRAM_BOT_TOKEN:
        return {
            "configured": False,
            "message": "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS environment variables"
        }
    
    # Get bot info
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{TELEGRAM_API_URL}/getMe")
            if response.status_code == 200:
                bot_info = response.json()
                return {
                    "configured": True,
                    "bot_username": bot_info.get("result", {}).get("username"),
                    "authorized_chats": AUTHORIZED_CHAT_IDS,
                    "webhook_url": f"/v1/telegram/webhook"
                }
    except Exception as e:
        logger.error(f"Failed to get bot info: {e}")
    
    return {"configured": True, "authorized_chats": AUTHORIZED_CHAT_IDS}


async def send_telegram_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> Dict:
    """Send a message via Telegram API."""
    if not TELEGRAM_API_URL:
        return {"error": "Telegram not configured"}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{TELEGRAM_API_URL}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                }
            )
            return response.json()
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return {"error": str(e)}


async def process_telegram_command(chat_id: int, text: str):
    """Process a Telegram command."""
    text = text.strip()
    
    # Parse command
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
    else:
        # Treat as a chat message
        command = "/chat"
        args = text
    
    # Route commands
    if command == "/start" or command == "/help":
        await send_telegram_message(chat_id, get_help_text())
    
    elif command == "/status":
        await send_status_update(chat_id)
    
    elif command == "/sessions":
        await send_sessions_list(chat_id)
    
    elif command == "/models":
        await send_models_list(chat_id)
    
    elif command == "/run":
        await handle_run_command(chat_id, args)
    
    elif command == "/chat":
        await handle_chat_command(chat_id, args)
    
    elif command == "/cancel":
        await handle_cancel_command(chat_id, args)
    
    else:
        await send_telegram_message(chat_id, f"Unknown command: {command}\n\n{get_help_text()}")


def get_help_text() -> str:
    """Get help text for Telegram bot."""
    return """
🤖 *DevForgeAI Bot*

Commands:
/status - System status
/sessions - Active sessions
/models - Available models
/run <agent> <task> - Start agent session
/cancel <session_id> - Cancel session
/chat <message> - Chat with default model
/help - Show this help

Examples:
`/run coder create a python script`
`/chat what is the capital of France?`
"""


async def send_status_update(chat_id: int):
    """Send system status update."""
    try:
        # Get health status
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("http://localhost:19000/v1/remote/health")
            if response.status_code == 200:
                health = response.json()
                
                status_text = f"""
🤖 *DevForgeAI Status*

Status: {health['status']}
Uptime: {health['uptime_seconds'] // 3600}h {(health['uptime_seconds'] % 3600) // 60}m
Models: {health['models_count']}
Personas: {health['personas_count']}
Agents: {health['agents_count']}
Sessions: {health['sessions_active']}

System:
CPU: {health['system']['cpu_percent']}%
Memory: {health['system']['memory_percent']}%
Disk: {health['system']['disk_percent']}%
"""
                await send_telegram_message(chat_id, status_text)
            else:
                await send_telegram_message(chat_id, "⚠️ Failed to get status")
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ Error: {e}")


async def send_sessions_list(chat_id: int):
    """Send list of active sessions."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("http://localhost:19000/v1/remote/sessions")
            if response.status_code == 200:
                sessions = response.json().get("data", [])
                
                if not sessions:
                    await send_telegram_message(chat_id, "No active sessions")
                    return
                
                text = "📋 *Sessions*\n\n"
                for s in sessions[:10]:  # Max 10
                    status_emoji = {"running": "🔄", "completed": "✅", "failed": "❌", "pending": "⏳"}.get(s["status"], "❓")
                    text += f"{status_emoji} `{s['session_id'][:8]}` - {s['agent_type']}: {s['task'][:30]}...\n"
                
                await send_telegram_message(chat_id, text)
            else:
                await send_telegram_message(chat_id, "⚠️ Failed to get sessions")
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ Error: {e}")


async def send_models_list(chat_id: int):
    """Send list of available models."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "http://localhost:19000/v1/models",
                headers={"Authorization": "Bearer modelmesh_local_dev_key"}
            )
            if response.status_code == 200:
                models = response.json().get("data", [])
                
                text = f"🤖 *{len(models)} Models Available*\n\n"
                
                # Group by provider
                providers = {}
                for m in models:
                    p = m.get("provider_name", "Unknown")
                    if p not in providers:
                        providers[p] = []
                    providers[p].append(m.get("display_name") or m.get("model_id"))
                
                for provider, model_list in providers.items():
                    text += f"*{provider}:*\n"
                    for m in model_list[:5]:  # Max 5 per provider
                        text += f"  • {m}\n"
                    if len(model_list) > 5:
                        text += f"  _...and {len(model_list) - 5} more_\n"
                    text += "\n"
                
                await send_telegram_message(chat_id, text)
            else:
                await send_telegram_message(chat_id, "⚠️ Failed to get models")
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ Error: {e}")


async def handle_run_command(chat_id: int, args: str):
    """Handle /run command to start an agent session."""
    if not args:
        await send_telegram_message(chat_id, "Usage: `/run <agent_type> <task>`\n\nAgent types: coder, researcher, designer, reviewer, planner, executor, writer")
        return
    
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await send_telegram_message(chat_id, "Usage: `/run <agent_type> <task>`")
        return
    
    agent_type, task = parts
    
    # Create session
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "http://localhost:19000/v1/remote/sessions",
                json={
                    "agent_type": agent_type,
                    "task": task,
                    "callback_url": f"http://localhost:19000/v1/telegram/callback/{chat_id}"
                }
            )
            if response.status_code == 200:
                session = response.json()
                await send_telegram_message(
                    chat_id,
                    f"✅ Session started\n\nID: `{session['session_id'][:8]}`\nAgent: {agent_type}\nTask: {task[:50]}..."
                )
            else:
                await send_telegram_message(chat_id, f"⚠️ Failed to start session")
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ Error: {e}")


async def handle_chat_command(chat_id: int, args: str):
    """Handle /chat command to chat with the default model."""
    if not args:
        await send_telegram_message(chat_id, "Usage: `/chat <message>`")
        return
    
    # For now, just acknowledge - full chat integration would need more work
    await send_telegram_message(chat_id, f"💭 You said: _{args}_\n\n(Chat integration coming soon)")


async def handle_cancel_command(chat_id: int, args: str):
    """Handle /cancel command."""
    if not args:
        await send_telegram_message(chat_id, "Usage: `/cancel <session_id>`")
        return
    
    session_id = args.strip()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"http://localhost:19000/v1/remote/sessions/{session_id}/cancel")
            if response.status_code == 200:
                await send_telegram_message(chat_id, f"✅ Session `{session_id}` cancelled")
            else:
                await send_telegram_message(chat_id, f"⚠️ Session not found or already completed")
    except Exception as e:
        await send_telegram_message(chat_id, f"⚠️ Error: {e}")