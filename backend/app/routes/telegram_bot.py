"""Telegram bot integration for remote DevForgeAI access."""

import asyncio
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

# Load from pydantic settings (reads .env file) then fall back to os.environ
def _load_telegram_config():
    from app.config import settings
    token = settings.telegram_bot_token or os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    chat_ids_str = settings.telegram_chat_ids or os.environ.get("TELEGRAM_CHAT_IDS") or ""
    # Sync into os.environ so any code that reads os.environ directly works too
    if token:
        os.environ["TELEGRAM_BOT_TOKEN"] = token
    if chat_ids_str:
        os.environ["TELEGRAM_CHAT_IDS"] = chat_ids_str
    chat_ids = [int(c.strip()) for c in chat_ids_str.split(",") if c.strip().lstrip("-").isdigit()]
    return token, chat_ids

_token, _chat_ids = _load_telegram_config()
TELEGRAM_BOT_TOKEN: str = _token
TELEGRAM_API_URL: str = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""
AUTHORIZED_CHAT_IDS: list = _chat_ids

# Per-chat conversation context (in-memory, persists while backend is up)
_telegram_conversations: dict = {}


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
        # Treat plain text as a chat message (most natural Telegram UX)
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
    
    elif command == "/continue":
        await handle_continue_command(chat_id)
    
    elif command == "/chat":
        await handle_chat_command(chat_id, args)
    
    elif command == "/image" or command == "/imagine" or command == "/img":
        await handle_image_command(chat_id, args)

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
/image <prompt> - Generate an image
/run <agent> <task> - Start agent session
/cancel <session_id> - Cancel session
/chat <message> - Chat (context kept per session)
/continue - Resume last conversation
/help - Show this help

Examples:
`/image a golden retriever skiing in Colorado`
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
    """Chat with the default persona, maintaining conversation context per Telegram chat."""
    if not args:
        await send_telegram_message(chat_id, "Usage: `/chat <message>`\nOr just send any message directly.")
        return

    await send_telegram_message(chat_id, "_Thinking..._")

    try:
        conv_id = _telegram_conversations.get(chat_id)

        # Resolve the default persona ID dynamically
        persona_id = "default"
        try:
            async with httpx.AsyncClient(timeout=5.0) as pc:
                pr = await pc.get(
                    "http://localhost:19000/v1/personas",
                    headers={"Authorization": "Bearer modelmesh_local_dev_key"}
                )
                if pr.status_code == 200:
                    personas = pr.json().get("data", [])
                    default_p = next((p for p in personas if p.get("is_default")), None) or (personas[0] if personas else None)
                    if default_p:
                        persona_id = default_p["id"]
        except Exception:
            pass

        body: dict = {
            "model": persona_id,
            "messages": [{"role": "user", "content": args}],
            "stream": False,
        }
        if conv_id:
            body["conversation_id"] = conv_id

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "http://localhost:19000/v1/chat/completions",
                json=body,
                headers={"Authorization": "Bearer modelmesh_local_dev_key"},
            )

        if response.status_code != 200:
            await send_telegram_message(chat_id, f"Error from AI: {response.text[:200]}")
            return

        data = response.json()
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "(no response)")
        new_conv_id = data.get("conversation_id") or (data.get("modelmesh") or {}).get("conversation_id")
        if new_conv_id:
            _telegram_conversations[chat_id] = new_conv_id

        model_used = data.get("model", "")
        footer = f"\n\n_via {model_used}_" if model_used else ""
        await send_telegram_message(chat_id, reply + footer)

    except Exception as e:
        logger.error(f"Chat command failed: {e}")
        await send_telegram_message(chat_id, f"Error: {str(e)[:200]}")

async def handle_continue_command(chat_id: int):
    """Resume the last conversation for this Telegram chat."""
    conv_id = _telegram_conversations.get(chat_id)
    if not conv_id:
        await send_telegram_message(chat_id, "No active conversation. Start one with /chat or just send a message.")
        return
    await send_telegram_message(chat_id, f"Continuing conversation `{conv_id[:8]}...`\nJust send your next message.")

async def handle_image_command(chat_id: int, args: str):
    """Handle /image command — submit an image gen task and deliver result back to Telegram."""
    if not args:
        await send_telegram_message(chat_id, "Usage: `/image <prompt>`\n\nExample:\n`/image a golden retriever skiing in Colorado`")
        return

    await send_telegram_message(chat_id, f"🎨 Generating image...\n\n_{args[:100]}_")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "http://localhost:19000/v1/tasks",
                json={
                    "task_type": "image_gen",
                    "params": {
                        "prompt": args,
                        "model": "gemini-imagen",
                        "size": "1024x1024",
                        "format": "png",
                    }
                },
                headers={"Authorization": "Bearer modelmesh_local_dev_key"},
            )
            if resp.status_code != 200:
                await send_telegram_message(chat_id, f"⚠️ Failed to submit image task: {resp.text[:200]}")
                return

            task = resp.json()
            task_id = task.get("id") or task.get("task_id")
            if not task_id:
                await send_telegram_message(chat_id, "⚠️ No task ID returned.")
                return

            # Poll until done (max 90 seconds)
            for _ in range(45):
                await asyncio.sleep(2)
                poll = await client.get(
                    f"http://localhost:19000/v1/tasks/{task_id}",
                    headers={"Authorization": "Bearer modelmesh_local_dev_key"},
                )
                if poll.status_code != 200:
                    continue
                data = poll.json()
                status = data.get("status")
                if status == "completed":
                    return  # _send_image_to_telegram already handles delivery
                elif status == "failed":
                    error = data.get("error") or data.get("user_message", "Unknown error")
                    await send_telegram_message(chat_id, f"❌ Image generation failed: {error[:200]}")
                    return

            await send_telegram_message(chat_id, "⏱️ Image is taking longer than expected — check the gallery when it's done.")

    except Exception as e:
        logger.error(f"Image command failed: {e}")
        await send_telegram_message(chat_id, f"⚠️ Error: {str(e)[:200]}")


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

@router.post("/register-webhook")
async def register_webhook(request: Request):
    """Register this server as the Telegram webhook."""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN not configured")

    # Try to determine our public URL
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    public_url = body.get("url")
    if not public_url:
        # Try to get Tailscale IP
        import socket
        try:
            hostname = socket.gethostname()
            tailscale_ip = None
            result = __import__("subprocess").run(
                ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                tailscale_ip = result.stdout.strip()
        except Exception:
            tailscale_ip = None

        base = f"http://{tailscale_ip}:19000" if tailscale_ip else "http://localhost:19000"
        public_url = f"{base}/v1/telegram/webhook"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API_URL}/setWebhook",
                json={"url": public_url, "allowed_updates": ["message", "edited_message"]}
            )
            data = resp.json()
            if data.get("ok"):
                return {"ok": True, "webhook_url": public_url, "description": data.get("description")}
            else:
                raise HTTPException(status_code=400, detail=f"Telegram rejected webhook: {data.get('description')}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/webhook")
async def delete_webhook():
    """Remove the Telegram webhook (switch to polling mode)."""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN not configured")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{TELEGRAM_API_URL}/deleteWebhook")
        return resp.json()


@router.get("/webhook-info")
async def get_webhook_info():
    """Get current webhook configuration from Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        return {"configured": False}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{TELEGRAM_API_URL}/getWebhookInfo")
        return resp.json().get("result", {})

# ─── Long-polling loop (runs as background task) ──────────────────────────────
_polling_task = None
_last_update_id: int = 0


async def _poll_loop():
    """Poll Telegram for updates every 2 seconds. Runs while backend is up."""
    global _last_update_id
    logger.info("Telegram polling loop started")

    while True:
        try:
            if not TELEGRAM_BOT_TOKEN or not TELEGRAM_API_URL:
                await asyncio.sleep(10)
                continue

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{TELEGRAM_API_URL}/getUpdates",
                    params={
                        "offset": _last_update_id + 1,
                        "timeout": 20,
                        "allowed_updates": ["message", "edited_message"],
                    }
                )

            if resp.status_code != 200:
                await asyncio.sleep(5)
                continue

            data = resp.json()
            if not data.get("ok"):
                await asyncio.sleep(5)
                continue

            updates = data.get("result", [])
            for update in updates:
                _last_update_id = update["update_id"]
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue

                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "").strip()

                if not chat_id or not text:
                    continue

                if not is_authorized(chat_id):
                    await send_telegram_message(chat_id, "Unauthorized.")
                    continue

                # Process in background so polling continues immediately
                asyncio.create_task(process_telegram_command(chat_id, text))

        except asyncio.CancelledError:
            logger.info("Telegram polling loop cancelled")
            break
        except Exception as e:
            logger.warning(f"Telegram poll error: {e}")
            await asyncio.sleep(5)


async def start_polling():
    """Start the polling loop as a background task."""
    global _polling_task
    # First delete any existing webhook so polling works
    if TELEGRAM_BOT_TOKEN and TELEGRAM_API_URL:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(f"{TELEGRAM_API_URL}/deleteWebhook")
            logger.info("Webhook cleared — polling mode active")
        except Exception as e:
            logger.warning(f"Could not clear webhook: {e}")

    _polling_task = asyncio.create_task(_poll_loop())


async def stop_polling():
    """Cancel the polling loop on shutdown."""
    global _polling_task
    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass