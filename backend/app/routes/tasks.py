"""Background task management — submit, poll, list, acknowledge."""

import uuid
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from app.database import get_db, AsyncSessionLocal
from app.models import Task
from app.middleware.auth import verify_api_key
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tasks", tags=["tasks"], dependencies=[Depends(verify_api_key)])


# ── Schemas ──────────────────────────────────────────────────────────────────

class TaskSubmit(BaseModel):
    task_type: str  # "image_gen"
    params: dict = {}
    conversation_id: Optional[str] = None

class TaskResponse(BaseModel):
    id: str
    task_type: str
    status: str
    params: dict
    result: Optional[dict] = None
    error: Optional[str] = None
    progress: int = 0
    user_message: Optional[str] = None
    conversation_id: Optional[str] = None
    acknowledged: int = 0
    created_at: str
    updated_at: Optional[str] = None

    @classmethod
    def from_orm(cls, obj):
        import uuid as _uuid
        from datetime import datetime
        d = {}
        for f in cls.model_fields:
            val = getattr(obj, f, None)
            if isinstance(val, _uuid.UUID): val = str(val)
            if isinstance(val, datetime): val = val.isoformat()
            d[f] = val
        return cls(**d)

class TaskListResponse(BaseModel):
    data: list[TaskResponse]
    total: int


# ── Background workers ──────────────────────────────────────────────────────

async def _run_image_gen(task_id: str, params: dict):
    """Generate an image in the background."""
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, uuid.UUID(task_id))
        if not task:
            return

        task.status = "running"
        task.user_message = "Starting image generation…"
        task.progress = 10
        await db.commit()

        try:
            prompt = params.get("prompt", "")
            model = params.get("model", "gemini-imagen")
            size = params.get("size", "1024x1024")
            negative_prompt = params.get("negative_prompt")
            workflow_id = params.get("workflow_id")
            checkpoint = params.get("checkpoint")
            lora = params.get("lora")
            lora_strength = params.get("lora_strength", 1.0)

            # Import image gen functions
            from app.routes.images import (
                ensure_comfyui, generate_with_comfyui,
                generate_with_gemini_imagen, IMAGE_STORAGE
            )
            from app.services.app_settings_helper import get_setting as _get_setting

            result = None
            used_model = model

            if model == "comfyui-local":
                comfyui_url = await _get_setting("comfyui_url", db)
                comfyui_dir = await _get_setting("comfyui_dir", db)
                task.user_message = "Checking ComfyUI…"
                task.progress = 20
                await db.commit()

                comfyui_available = await ensure_comfyui(comfyui_url)
                if comfyui_available:
                    task.user_message = f"Generating with ComfyUI ({workflow_id or 'sdxl-standard'})…"
                    task.progress = 40
                    await db.commit()

                    # Throttle DB writes so we don't commit on every WS event
                    _last_update = {"ts": 0.0}

                    async def _report_progress(message: str, percent):
                        """Update task.user_message + progress from ComfyUI WS events."""
                        import time as _t
                        now = _t.monotonic()
                        if now - _last_update["ts"] < 0.4:
                            return  # throttle: at most ~2.5 updates/sec
                        _last_update["ts"] = now
                        try:
                            task.user_message = f"ComfyUI: {message}"
                            if percent is not None:
                                # Map 0-100 into our 40-90 task progress band
                                task.progress = 40 + int(percent * 0.5)
                            await db.commit()
                        except Exception:
                            pass  # non-fatal

                    try:
                        result = await generate_with_comfyui(
                            prompt=prompt,
                            comfyui_url=comfyui_url,
                            workflow_id=workflow_id,
                            comfyui_dir=comfyui_dir,
                            progress_cb=_report_progress,
                        )
                    except Exception as comfy_err:
                        err_detail = str(comfy_err)
                        # Extract useful detail from HTTPException
                        if hasattr(comfy_err, 'detail'):
                            err_detail = str(comfy_err.detail)
                        logger.error(f"ComfyUI generation failed: {err_detail}")
                        task.user_message = f"ComfyUI error: {err_detail[:120]}. Falling back to Gemini…"
                        task.progress = 35
                        await db.commit()
                        used_model = "gemini-imagen"
                else:
                    logger.warning("ComfyUI not reachable, falling back to Gemini")
                    task.user_message = "ComfyUI unavailable, falling back to Gemini…"
                    task.progress = 30
                    await db.commit()
                    used_model = "gemini-imagen"

            if used_model == "gemini-imagen" or (model == "gemini-imagen" and result is None):
                api_key = (os.environ.get('GEMINI_API_KEY')
                           or os.environ.get('GOOGLE_API_KEY')
                           or getattr(settings, 'gemini_api_key', None))
                if not api_key:
                    raise ValueError("No Gemini API key configured for image generation")
                task.user_message = "Generating with Gemini Imagen…"
                task.progress = 50
                await db.commit()
                result = await generate_with_gemini_imagen(prompt, api_key, size)
                used_model = "gemini-imagen"

            if result is None:
                raise ValueError(f"Unknown image model: {model}")

            # Store image in memory
            image_id = str(uuid.uuid4())
            width, height = map(int, size.split('x'))
            from app.routes.images import _store_image
            _store_image(image_id, {
                "base64": result["base64"],
                "prompt": prompt,
                "revised_prompt": result.get("revised_prompt"),
                "format": params.get("format", "png"),
                "size": size,
                "model": used_model,
                "negative_prompt": negative_prompt,
            })

            task.status = "completed"
            task.progress = 100
            task.user_message = f"Image generated with {used_model}"
            task.result = {
                "image_id": image_id,
                "url": f"/v1/img/{image_id}",
                "prompt": prompt,
                "revised_prompt": result.get("revised_prompt"),
                "model": used_model,
                "width": width,
                "height": height,
            }
            await db.commit()
            logger.info(f"Task {task_id} completed: image {image_id}")

            # Send image to Telegram if configured
            asyncio.create_task(_send_image_to_telegram(
                image_id=image_id,
                image_b64=result["base64"],
                fmt=params.get("format", "png"),
                prompt=prompt,
                model=used_model,
            ))

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            task.status = "failed"
            task.error = str(e)[:500]
            task.user_message = f"Failed: {str(e)[:100]}"
            task.progress = 0
            await db.commit()


async def _send_image_to_telegram(image_id: str, image_b64: str, fmt: str, prompt: str, model: str):
    """Send a completed image to all configured Telegram chats."""
    try:
        from app.routes.telegram_bot import TELEGRAM_BOT_TOKEN, TELEGRAM_API_URL, AUTHORIZED_CHAT_IDS
        if not TELEGRAM_BOT_TOKEN or not AUTHORIZED_CHAT_IDS:
            return  # Telegram not configured

        import base64
        import httpx
        image_bytes = base64.b64decode(image_b64)
        caption = f"🎨 *Image Ready*\n\n_{prompt[:200]}{'...' if len(prompt) > 200 else ''}_\n\n`{model}`"

        async with httpx.AsyncClient(timeout=30.0) as client:
            for chat_id in AUTHORIZED_CHAT_IDS:
                try:
                    resp = await client.post(
                        f"{TELEGRAM_API_URL}/sendPhoto",
                        data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
                        files={"photo": (f"{image_id}.{fmt}", image_bytes, f"image/{fmt}")},
                    )
                    if resp.status_code == 200:
                        logger.info(f"Image {image_id} sent to Telegram chat {chat_id}")
                    else:
                        logger.warning(f"Telegram sendPhoto failed for chat {chat_id}: {resp.text[:200]}")
                except Exception as e:
                    logger.warning(f"Failed to send image to Telegram chat {chat_id}: {e}")
    except Exception as e:
        logger.warning(f"Telegram image delivery skipped: {e}")


# Worker dispatch
TASK_WORKERS = {
    "image_gen": _run_image_gen,
}


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("", response_model=TaskResponse)
async def submit_task(
    req: TaskSubmit,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Submit a background task. Returns immediately with task ID."""
    if req.task_type not in TASK_WORKERS:
        raise HTTPException(400, f"Unknown task type: {req.task_type}. Available: {list(TASK_WORKERS)}")

    task = Task(
        task_type=req.task_type,
        status="pending",
        params=req.params,
        conversation_id=req.conversation_id,
        user_message="Queued…",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Launch in background
    background_tasks.add_task(TASK_WORKERS[req.task_type], str(task.id), req.params)

    return TaskResponse.from_orm(task)


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[str] = Query(None),
    unacknowledged: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List tasks, optionally filtered."""
    query = select(Task).order_by(Task.created_at.desc())
    if status:
        query = query.where(Task.status == status)
    if unacknowledged:
        query = query.where(Task.acknowledged == 0, Task.status.in_(["completed", "failed"]))
    query = query.limit(limit)

    result = await db.execute(query)
    tasks = result.scalars().all()
    return TaskListResponse(
        data=[TaskResponse.from_orm(t) for t in tasks],
        total=len(tasks),
    )


@router.get("/notifications")
async def get_notifications(db: AsyncSession = Depends(get_db)):
    """Get unacknowledged completed/failed tasks — used for toast notifications."""
    query = select(Task).where(
        Task.acknowledged == 0,
        Task.status.in_(["completed", "failed"])
    ).order_by(Task.created_at.desc()).limit(10)
    result = await db.execute(query)
    tasks = result.scalars().all()
    return {"notifications": [TaskResponse.from_orm(t) for t in tasks]}


@router.post("/{task_id}/acknowledge")
async def acknowledge_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Mark a task notification as seen."""
    task = await db.get(Task, uuid.UUID(task_id))
    if not task:
        raise HTTPException(404, "Task not found")
    task.acknowledged = 1
    await db.commit()
    return {"status": "acknowledged"}


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single task by ID."""
    task = await db.get(Task, uuid.UUID(task_id))
    if not task:
        raise HTTPException(404, "Task not found")
    return TaskResponse.from_orm(task)
