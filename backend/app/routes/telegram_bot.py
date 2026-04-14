"""Telegram bot integration for remote DevForgeAI access."""

import asyncio
import base64
import httpx
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import logging
import mimetypes
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
_telegram_pending_images: dict = {}
_internal_api_base_url: str = ""


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


def _get_auth_headers() -> Dict[str, str]:
    """Auth headers for internal API calls back into DevForgeAI."""
    from app.config import settings
    return {"Authorization": f"Bearer {settings.modelmesh_api_key}"}


def _remember_internal_api_base(base_url: str):
    """Remember the currently serving backend URL for follow-up Telegram actions."""
    global _internal_api_base_url
    if base_url:
        _internal_api_base_url = base_url.rstrip("/")


async def _resolve_internal_api_base_url(force_refresh: bool = False) -> str:
    """Resolve the active DevForgeAI backend URL instead of assuming a fixed port."""
    global _internal_api_base_url

    configured = (
        os.environ.get("DEVFORGEAI_INTERNAL_BASE_URL")
        or os.environ.get("MODELMESH_INTERNAL_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if configured:
        _internal_api_base_url = configured
        return configured

    if _internal_api_base_url and not force_refresh:
        return _internal_api_base_url

    candidates = [
        "http://127.0.0.1:19001",
        "http://localhost:19001",
        "http://127.0.0.1:19000",
        "http://localhost:19000",
    ]
    seen = set()

    async with httpx.AsyncClient(timeout=3.0) as client:
        for base in candidates:
            if base in seen:
                continue
            seen.add(base)
            try:
                response = await client.get(f"{base}/health")
                if response.status_code == 200:
                    _internal_api_base_url = base
                    return base
            except Exception:
                continue

    fallback = candidates[0]
    _internal_api_base_url = fallback
    return fallback


async def _internal_api_request(method: str, path: str, **kwargs) -> httpx.Response:
    """Issue an internal API request against the active backend."""
    base_url = await _resolve_internal_api_base_url()
    timeout = kwargs.pop("timeout", 30.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(method, f"{base_url}{path}", **kwargs)
    except Exception:
        retry_base = await _resolve_internal_api_base_url(force_refresh=True)
        if retry_base != base_url:
            async with httpx.AsyncClient(timeout=timeout) as client:
                return await client.request(method, f"{retry_base}{path}", **kwargs)
        raise


def _extract_message_text(message: Dict[str, Any]) -> str:
    """Return either text or caption from a Telegram message."""
    return (message.get("text") or message.get("caption") or "").strip()


def _extract_image_attachment(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Select the best Telegram image attachment from a message."""
    photos = message.get("photo") or []
    if photos:
        best = max(photos, key=lambda item: item.get("file_size", 0))
        return {
            "file_id": best.get("file_id"),
            "filename": f"telegram-photo-{best.get('file_unique_id') or 'image'}.jpg",
            "mime_type": "image/jpeg",
            "file_size": best.get("file_size") or 0,
            "kind": "photo",
        }

    document = message.get("document") or {}
    mime_type = (document.get("mime_type") or "").lower()
    if document.get("file_id") and mime_type.startswith("image/"):
        return {
            "file_id": document.get("file_id"),
            "filename": document.get("file_name") or f"telegram-image-{document.get('file_unique_id') or 'image'}",
            "mime_type": mime_type,
            "file_size": document.get("file_size") or 0,
            "kind": "document",
        }

    return None


async def _download_telegram_file(file_id: str, fallback_name: str = "telegram-image") -> Dict[str, Any]:
    """Download a file payload from Telegram by file id."""
    if not TELEGRAM_API_URL or not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Telegram bot is not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        meta_resp = await client.get(f"{TELEGRAM_API_URL}/getFile", params={"file_id": file_id})
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        if not meta.get("ok"):
            raise RuntimeError(meta.get("description") or "Telegram getFile failed")

        file_path = (meta.get("result") or {}).get("file_path")
        if not file_path:
            raise RuntimeError("Telegram did not return a file path")

        file_resp = await client.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}")
        file_resp.raise_for_status()

    guessed_mime = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    filename = os.path.basename(file_path) or fallback_name
    return {
        "bytes": file_resp.content,
        "mime_type": guessed_mime,
        "filename": filename,
        "file_path": file_path,
    }


async def _upload_image_to_devforge(image_bytes: bytes, mime_type: str, filename: str) -> Dict[str, Any]:
    """Store an inbound Telegram image in DevForgeAI's image gallery."""
    response = await _internal_api_request(
        "POST",
        "/v1/images/upload",
        headers=_get_auth_headers(),
        json={
            "base64": base64.b64encode(image_bytes).decode("utf-8"),
            "filename": filename,
            "mime_type": mime_type,
        },
        timeout=60.0,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Image upload failed: {response.text[:200]}")
    return response.json()


async def _fetch_internal_image_bytes(image_id: str) -> Dict[str, Any]:
    """Fetch an image binary from the active backend for Telegram delivery."""
    response = await _internal_api_request(
        "GET",
        f"/v1/images/{image_id}/download",
        headers=_get_auth_headers(),
        timeout=60.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Image download failed: {response.text[:200]}")

    content_type = response.headers.get("content-type", "image/png")
    extension = mimetypes.guess_extension(content_type) or ".png"
    if extension == ".jpe":
        extension = ".jpg"

    return {
        "bytes": response.content,
        "mime_type": content_type,
        "filename": f"{image_id}{extension}",
    }


async def send_telegram_photo(
    chat_id: int,
    image_bytes: bytes,
    filename: str = "image.png",
    mime_type: str = "image/png",
    caption: Optional[str] = None,
    parse_mode: str = "Markdown",
) -> Dict[str, Any]:
    """Send an image to a Telegram chat."""
    if not TELEGRAM_API_URL:
        return {"error": "Telegram not configured"}

    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption
        data["parse_mode"] = parse_mode

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{TELEGRAM_API_URL}/sendPhoto",
                data=data,
                files={"photo": (filename, image_bytes, mime_type)},
            )
            return response.json()
    except Exception as e:
        logger.error(f"Failed to send Telegram photo: {e}")
        return {"error": str(e)}


async def _edit_telegram_image(chat_id: int, prompt: str, source_image_id: str):
    """Run a reimagine/edit request using the last Telegram image for this chat."""
    await send_telegram_message(chat_id, f"🖼️ Reimagining image...\n\n_{prompt[:160]}_")

    response = await _internal_api_request(
        "POST",
        "/v1/images/edit",
        headers=_get_auth_headers(),
        json={
            "source_image_id": source_image_id,
            "prompt": prompt,
        },
        timeout=180.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Image edit failed: {response.text[:200]}")

    payload = response.json()
    images = payload.get("data") or []
    if not images:
        raise RuntimeError("Image edit did not return any images")

    image_data = images[0]
    image_id = image_data.get("id")
    if not image_id:
        raise RuntimeError("Edited image response did not include an id")

    binary = await _fetch_internal_image_bytes(image_id)
    caption = f"🖼️ *Reimagined Image*\n\n_{prompt[:200]}{'...' if len(prompt) > 200 else ''}_"
    await send_telegram_photo(
        chat_id,
        binary["bytes"],
        filename=binary["filename"],
        mime_type=binary["mime_type"],
        caption=caption,
    )

    _telegram_pending_images[chat_id] = {
        "source_image_id": image_id,
        "filename": binary["filename"],
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


async def process_telegram_media_message(chat_id: int, message: Dict[str, Any]):
    """Process an inbound Telegram image and optionally reimagine it immediately."""
    attachment = _extract_image_attachment(message)
    if not attachment:
        await send_telegram_message(chat_id, "⚠️ I can only process image attachments right now.")
        return

    if attachment.get("file_size", 0) > 25 * 1024 * 1024:
        await send_telegram_message(chat_id, "⚠️ That image is too large for Telegram processing. Keep it under 25 MB.")
        return

    incoming_text = _extract_message_text(message)

    try:
        downloaded = await _download_telegram_file(
            attachment["file_id"],
            fallback_name=attachment.get("filename") or "telegram-image",
        )
        upload = await _upload_image_to_devforge(
            downloaded["bytes"],
            attachment.get("mime_type") or downloaded["mime_type"],
            attachment.get("filename") or downloaded["filename"],
        )
        source_image_id = upload.get("id")
        if not source_image_id:
            raise RuntimeError("DevForgeAI did not return an image id for the uploaded Telegram photo")

        _telegram_pending_images[chat_id] = {
            "source_image_id": source_image_id,
            "filename": attachment.get("filename") or downloaded["filename"],
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

        if incoming_text:
            if incoming_text.startswith("/"):
                parts = incoming_text.split(maxsplit=1)
                command = parts[0].split("@", 1)[0].lower()
                args = parts[1].strip() if len(parts) > 1 else ""
                if command in {"/image", "/imagine", "/img"}:
                    await handle_image_command(chat_id, args, source_image_id=source_image_id)
                    return
            else:
                await handle_image_command(chat_id, incoming_text, source_image_id=source_image_id)
                return

        await send_telegram_message(
            chat_id,
            "📥 Image received. Send `/image <prompt>` or just reply with what to change, and I’ll reimagine the last image you sent.",
        )
    except Exception as e:
        logger.error(f"Telegram image processing failed: {e}")
        await send_telegram_message(chat_id, f"⚠️ Failed to process that image: {str(e)[:200]}")


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """Handle incoming Telegram webhook."""
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram bot not configured")
    
    try:
        _remember_internal_api_base(str(request.base_url))
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
    text = _extract_message_text(message)
    attachment = _extract_image_attachment(message)
    
    if not chat_id or (not text and not attachment):
        return {"status": "ok", "message": "No supported chat content"}
    
    # Check authorization
    if not is_authorized(chat_id):
        await send_telegram_message(chat_id, "⚠️ Unauthorized access")
        return {"status": "unauthorized"}
    
    # Process command in background
    if attachment:
        background_tasks.add_task(process_telegram_media_message, chat_id, message)
    else:
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
        command = parts[0].split("@", 1)[0].lower()
        args = parts[1] if len(parts) > 1 else ""
    else:
        # If the user recently uploaded an image, treat follow-up text as an edit prompt.
        command = "/image" if chat_id in _telegram_pending_images else "/chat"
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
/image <prompt> + photo - Reimagine the attached or last-uploaded image
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
        response = await _internal_api_request("GET", "/v1/remote/health", timeout=10.0)
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
        response = await _internal_api_request("GET", "/v1/remote/sessions", timeout=10.0)
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
        response = await _internal_api_request(
            "GET",
            "/v1/models",
            headers=_get_auth_headers(),
            timeout=10.0,
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
        internal_base = await _resolve_internal_api_base_url()
        response = await _internal_api_request(
            "POST",
            "/v1/remote/sessions",
            json={
                "agent_type": agent_type,
                "task": task,
                "callback_url": f"{internal_base}/v1/telegram/callback/{chat_id}"
            },
            timeout=10.0,
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
            pr = await _internal_api_request(
                "GET",
                "/v1/personas",
                headers=_get_auth_headers(),
                timeout=5.0,
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

        response = await _internal_api_request(
            "POST",
            "/v1/chat/completions",
            json=body,
            headers=_get_auth_headers(),
            timeout=60.0,
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

async def handle_image_command(chat_id: int, args: str, source_image_id: Optional[str] = None):
    """Handle /image command — submit an image gen task and deliver result back to Telegram."""
    if not args:
        await send_telegram_message(chat_id, "Usage: `/image <prompt>`\n\nExample:\n`/image a golden retriever skiing in Colorado`")
        return

    try:
        pending = _telegram_pending_images.get(chat_id) or {}
        source_image_id = source_image_id or pending.get("source_image_id")

        if source_image_id:
            await _edit_telegram_image(chat_id, args, source_image_id)
            return

        await send_telegram_message(chat_id, f"🎨 Generating image...\n\n_{args[:100]}_")

        resp = await _internal_api_request(
            "POST",
            "/v1/tasks",
            json={
                "task_type": "image_gen",
                "params": {
                    "prompt": args,
                    "model": "gemini-imagen",
                    "size": "1024x1024",
                    "format": "png",
                }
            },
            headers=_get_auth_headers(),
            timeout=10.0,
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
            poll = await _internal_api_request(
                "GET",
                f"/v1/tasks/{task_id}",
                headers=_get_auth_headers(),
                timeout=10.0,
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
        response = await _internal_api_request(
            "POST",
            f"/v1/remote/sessions/{session_id}/cancel",
            timeout=10.0,
        )
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

        base = f"http://{tailscale_ip}:19001" if tailscale_ip else (str(request.base_url).rstrip("/") if request else "http://localhost:19001")
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
                text = _extract_message_text(message)
                attachment = _extract_image_attachment(message)

                if not chat_id or (not text and not attachment):
                    continue

                if not is_authorized(chat_id):
                    await send_telegram_message(chat_id, "Unauthorized.")
                    continue

                # Process in background so polling continues immediately
                if attachment:
                    asyncio.create_task(process_telegram_media_message(chat_id, message))
                else:
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