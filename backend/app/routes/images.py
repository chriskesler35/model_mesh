"""Image generation endpoints using Gemini Imagen and ComfyUI."""

import uuid
import base64
import httpx
import logging
import asyncio
import subprocess
import sys
import json
import random
import shlex
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Model
from app.middleware.auth import verify_api_key
from app.config import settings
from app.services.app_settings_helper import get_setting
from app.routes.workflows import find_workflow_path, _convert_editor_to_api, _fetch_object_info_schema, _get_running_comfyui_url
from pydantic import BaseModel
from typing import Optional, List, Tuple, Any, Dict
from datetime import datetime as _dt
import os

logger = logging.getLogger(__name__)

# ─── Async Job Store ──────────────────────────────────────────────────────────
# Lightweight in-memory store for background generation jobs.
# Survives the request lifecycle so the frontend can poll progress even after
# the originating fetch returns a job_id immediately.
_JOB_STORE: Dict[str, Dict[str, Any]] = {}


def _job_create(job_id: str, kind: str, source_image_id: str = None) -> dict:
    job: Dict[str, Any] = {
        "id": job_id,
        "kind": kind,               # "variation" | "generation"
        "status": "pending",        # pending | running | complete | error
        "step": 0,
        "max_steps": 0,
        "message": "Queued…",
        "source_image_id": source_image_id,
        "result_id": None,          # set on completion
        "error": None,
        "created_at": _dt.utcnow().isoformat() + "Z",
        "updated_at": _dt.utcnow().isoformat() + "Z",
    }
    _JOB_STORE[job_id] = job
    return job


def _job_update(job_id: str, **kwargs) -> None:
    job = _JOB_STORE.get(job_id)
    if job:
        job.update(kwargs)
        job["updated_at"] = _dt.utcnow().isoformat() + "Z"


def _make_job_progress_cb(job_id: str):
    """Return an async progress_cb that writes step info into the job store."""
    import re as _re
    _step_pat = _re.compile(r"Sampling step (\d+)/(\d+)")

    async def _cb(message: str, percent: int | None) -> None:
        updates: Dict[str, Any] = {"status": "running", "message": message}
        m = _step_pat.match(message)
        if m:
            updates["step"] = int(m.group(1))
            updates["max_steps"] = int(m.group(2))
        elif percent is not None:
            updates["step"] = percent
            updates["max_steps"] = 100
        _job_update(job_id, **updates)

    return _cb


async def _stop_comfyui_progress_task(ws_stop_event: "asyncio.Event", ws_task) -> None:
    """Stop the background ComfyUI progress stream task if it is running."""
    ws_stop_event.set()
    if ws_task:
        try:
            await asyncio.wait_for(ws_task, timeout=1.0)
        except Exception:
            pass


async def _cancel_comfyui_prompt(client: httpx.AsyncClient, comfyui_url: str, prompt_id: str) -> None:
    """Best-effort cleanup for an abandoned ComfyUI prompt.

    If the prompt is actively running, request an interrupt. If it is still
    pending, remove it from the queue. This prevents stale jobs from blocking
    later frontend requests after timeouts, disconnects, or backend restarts.
    """
    try:
        is_running = False
        queue_resp = await client.get(f"{comfyui_url}/queue")
        if queue_resp.status_code == 200:
            queue_data = queue_resp.json()
            for item in queue_data.get("queue_running", []):
                if isinstance(item, list) and len(item) > 1 and item[1] == prompt_id:
                    is_running = True
                    break

        if is_running:
            interrupt_resp = await client.post(f"{comfyui_url}/interrupt")
            logger.info(
                "Requested ComfyUI interrupt for prompt %s (status=%s)",
                prompt_id,
                interrupt_resp.status_code,
            )

        delete_resp = await client.post(f"{comfyui_url}/queue", json={"delete": [prompt_id]})
        logger.info(
            "Requested ComfyUI queue cleanup for prompt %s (status=%s)",
            prompt_id,
            delete_resp.status_code,
        )
    except Exception as e:
        logger.warning("Failed to clean up ComfyUI prompt %s: %s", prompt_id, e)


def _extract_comfyui_file_refs(node_output: dict) -> list[dict]:
    """Collect file-like outputs from a ComfyUI history node output."""
    refs = []
    for key in ("images", "gifs", "audio", "videos", "files"):
        values = node_output.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict) and item.get("filename"):
                refs.append(item)
    return refs

# ─── ComfyUI auto-launch ──────────────────────────────────────────────────────

# ComfyUI paths are now configurable via Settings > Image Generation
# Priority: DB settings > .env > defaults (empty = disabled)
_comfyui_proc: Optional[subprocess.Popen] = None
_comfyui_rr_index: int = 0


def _parse_comfyui_urls(url_value: str) -> List[str]:
    """Parse configured ComfyUI URL(s) into a normalized list.

    Supports comma/semicolon/newline separated values, e.g.
    "http://127.0.0.1:8188, http://127.0.0.1:8189".
    """
    raw = (url_value or "").strip()
    if not raw:
        return ["http://localhost:8188"]

    parts: List[str] = []
    for chunk in raw.replace(";", ",").replace("\n", ",").split(","):
        url = chunk.strip().rstrip("/")
        if url and url not in parts:
            parts.append(url)
    return parts or ["http://localhost:8188"]


async def _resolve_comfyui_endpoint(configured_url_value: str) -> Optional[str]:
    """Choose a reachable ComfyUI endpoint using least-load + failover.

    Behavior:
    - Prefer the least-busy healthy endpoint from configured URL list.
    - Tie-break by round-robin order for fairness.
    - Attempt auto-launch only on the first configured endpoint.
    - Fall back to any endpoint that becomes healthy after launch attempt.
    """
    global _comfyui_rr_index

    async def _queue_load(url: str) -> Optional[Tuple[int, int, int]]:
        """Return (total, pending, running) load from /queue, or None if unhealthy."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{url}/queue")
            if r.status_code != 200:
                return None
            data = r.json()
            running = len(data.get("queue_running", []) or [])
            pending = len(data.get("queue_pending", []) or [])
            return (running + pending, pending, running)
        except Exception:
            return None

    urls = _parse_comfyui_urls(configured_url_value)
    if not urls:
        return None

    start = _comfyui_rr_index % len(urls)
    _comfyui_rr_index += 1
    ordered = urls[start:] + urls[:start]

    candidates: List[Tuple[Tuple[int, int, int], str]] = []
    for url in ordered:
        load = await _queue_load(url)
        if load is not None:
            candidates.append((load, url))

    if candidates:
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    primary = urls[0]
    if await ensure_comfyui(primary):
        return primary

    candidates = []
    for url in ordered:
        load = await _queue_load(url)
        if load is not None:
            candidates.append((load, url))

    if candidates:
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    return None


async def _get_comfyui_paths():
    """Load ComfyUI paths from DB settings."""
    from app.database import AsyncSessionLocal
    from app.services.app_settings_helper import get_comfyui_config
    try:
        async with AsyncSessionLocal() as db:
            cfg = await get_comfyui_config(db)
            return cfg
    except Exception:
        return {
            "dir": "",
            "python": "",
            "url": "http://localhost:8188",
            "gpu_devices": "0",
            "launch_args": "",
        }


async def is_comfyui_running(url: str = "http://localhost:8188") -> bool:
    """Quick TCP health-check against ComfyUI."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{url}/system_stats")
            return r.status_code == 200
    except Exception:
        return False


def _has_cli_flag(args: list[str], flag: str) -> bool:
    return any(arg == flag or arg.startswith(f"{flag}=") for arg in args)


def _build_comfyui_launch_cmd(comfyui_python: Path, launch_args: str) -> list[str]:
    cmd = [str(comfyui_python), "main.py"]
    user_args = shlex.split(launch_args, posix=False) if launch_args else []

    if not _has_cli_flag(user_args, "--listen"):
        cmd.extend(["--listen", "0.0.0.0"])
    if not _has_cli_flag(user_args, "--default-device"):
        # Primary GPU, keeps others visible for overflow.
        cmd.extend(["--default-device", "0"])
    if not _has_cli_flag(user_args, "--preview-method"):
        cmd.extend(["--preview-method", "auto"])
    if not _has_cli_flag(user_args, "--enable-cors-header"):
        cmd.extend(["--enable-cors-header", "*"])

    cmd.extend(user_args)
    return cmd


async def launch_comfyui(url: str = "http://localhost:8188") -> bool:
    """
    Spawn ComfyUI in the background (Windows detached process).
    Returns True if it becomes reachable within ~45 s, False otherwise.
    """
    global _comfyui_proc
    logger.info("ComfyUI not running — attempting auto-launch…")

    cfg = await _get_comfyui_paths()
    comfyui_dir = Path(cfg["dir"]) if cfg["dir"] else None
    comfyui_python = Path(cfg["python"]) if cfg["python"] else None

    if not comfyui_dir or not comfyui_dir.exists():
        logger.warning(f"ComfyUI directory not configured or not found: {comfyui_dir}")
        return False
    if not comfyui_python or not comfyui_python.exists():
        # Fallback: try 'python' on PATH
        comfyui_python = Path("python")
        logger.info("ComfyUI python not configured, trying system python")

    env = os.environ.copy()
    gpu_devices = cfg.get("gpu_devices", "0")
    launch_args = (cfg.get("launch_args") or "").strip()
    env["CUDA_VISIBLE_DEVICES"] = gpu_devices
    # Performance env vars
    env["NVIDIA_TF32_OVERRIDE"] = "1"
    env["CUDA_MODULE_LOADING"] = "LAZY"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    cmd = _build_comfyui_launch_cmd(comfyui_python, launch_args)
    logger.info(
        "Launching ComfyUI: CUDA_VISIBLE_DEVICES=%s, cwd=%s, args=%s",
        gpu_devices,
        comfyui_dir,
        " ".join(cmd[2:]),
    )

    try:
        _comfyui_proc = subprocess.Popen(
            cmd,
            cwd=str(comfyui_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        logger.info(f"ComfyUI launched (pid {_comfyui_proc.pid}), waiting for ready…")
    except Exception as e:
        logger.error(f"Failed to launch ComfyUI: {e}")
        return False

    # Poll until ready (max 45 s)
    for _ in range(45):
        await asyncio.sleep(1)
        if await is_comfyui_running(url):
            logger.info("ComfyUI is ready ✓")
            return True

    logger.warning("ComfyUI launched but did not become ready in 45s")
    return False


async def ensure_comfyui(url: str = "http://localhost:8188") -> bool:
    """Check if ComfyUI is running; auto-launch if not. Returns True if available."""
    logger.info(f"Checking ComfyUI at {url}")
    if await is_comfyui_running(url):
        logger.info(f"ComfyUI is running at {url}")
        return True
    logger.warning(f"ComfyUI not responding at {url}, attempting auto-launch")
    return await launch_comfyui(url)

router = APIRouter(prefix="/v1/images", tags=["images"], dependencies=[Depends(verify_api_key)])

# Public router for serving images (no auth needed for <img src> tags)
public_router = APIRouter(prefix="/v1/img", tags=["images"])


class ImageGenerationRequest(BaseModel):
    model: str  # "gemini-imagen" or "comfyui-local"
    prompt: str
    size: str = "1024x1024"
    format: str = "png"
    style: Optional[str] = None
    num_variations: int = 1
    negative_prompt: Optional[str] = None
    workflow_id: Optional[str] = None  # which workflow template to use
    checkpoint: Optional[str] = None   # which checkpoint/model to use
    lora: Optional[str] = None         # LoRA model name
    lora_strength: float = 1.0         # LoRA model/clip strength


class ImageResponse(BaseModel):
    id: str
    url: str
    revised_prompt: Optional[str] = None
    width: int
    height: int
    format: str
    prompt: Optional[str] = None
    model: Optional[str] = None
    created_at: Optional[str] = None
    variation_of: Optional[str] = None


class ImageListResponse(BaseModel):
    data: List[ImageResponse]
    total: int


# In-memory storage for generated images (use proper storage in production)
# Persistent image storage on disk
_IMAGE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "images"
_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
_IMAGE_META = _IMAGE_DIR / "_meta.json"

def _load_image_storage() -> dict:
    """Load image metadata from disk."""
    if _IMAGE_META.exists():
        import json
        try:
            return json.loads(_IMAGE_META.read_text())
        except Exception:
            return {}
    return {}

def _save_image_storage(storage: dict):
    """Save image metadata to disk."""
    import json
    # Save metadata (without base64 — that's in separate files)
    meta = {}
    for k, v in storage.items():
        meta[k] = {key: val for key, val in v.items() if key != "base64"}
    _IMAGE_META.write_text(json.dumps(meta, indent=2))

def _store_image(image_id: str, data: dict):
    """Store image binary + metadata to disk, then free base64 from memory."""
    # Save binary
    img_bytes = base64.b64decode(data["base64"])
    fmt = data.get("format", "png")
    (_IMAGE_DIR / f"{image_id}.{fmt}").write_bytes(img_bytes)
    # Update in-memory + metadata — drop base64 to prevent memory bloat
    IMAGE_STORAGE[image_id] = {k: v for k, v in data.items() if k != "base64"}
    IMAGE_STORAGE[image_id]["base64"] = ""  # lazy-loaded from disk on demand
    _save_image_storage(IMAGE_STORAGE)

def _load_image_base64(image_id: str, fmt: str = "png") -> str:
    """Load image binary from disk as base64."""
    for ext in [fmt, "png", "jpg", "jpeg", "webp"]:
        p = _IMAGE_DIR / f"{image_id}.{ext}"
        if p.exists():
            return base64.b64encode(p.read_bytes()).decode("utf-8")
    return ""

# In-memory cache, bootstrapped from disk
IMAGE_STORAGE = _load_image_storage()
# Patch base64 loader
for _id in IMAGE_STORAGE:
    if "base64" not in IMAGE_STORAGE[_id]:
        IMAGE_STORAGE[_id]["base64"] = ""  # lazy-loaded


async def generate_with_gemini_imagen(prompt: str, api_key: str, size: str = "1024x1024") -> dict:
    """Generate image using Gemini's image generation model via REST API."""
    try:
        # Use gemini-2.5-flash-image (Nano Banana) which supports image generation
        model_name = "gemini-2.5-flash-image"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

        # Prefix prompt to force image generation (not text description)
        gen_prompt = f"Generate an image: {prompt}"

        payload = {
            "contents": [{"parts": [{"text": gen_prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
            },
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload, headers={"Content-Type": "application/json"})

            if response.status_code != 200:
                error_msg = response.text[:200]
                raise HTTPException(status_code=response.status_code, detail=f"Gemini image generation failed: {error_msg}")

            data = response.json()

        # Extract image from response
        candidates = data.get("candidates", [])
        if not candidates:
            raise HTTPException(status_code=500, detail="Gemini returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            inline_data = part.get("inlineData")
            if inline_data and inline_data.get("mimeType", "").startswith("image/"):
                return {
                    "base64": inline_data["data"],
                    "revised_prompt": prompt,
                }

        # If no image part found, check for text explanation
        text_parts = [p.get("text", "") for p in parts if "text" in p]
        detail = " ".join(text_parts) if text_parts else "No image in response"
        raise HTTPException(status_code=500, detail=f"Gemini did not return an image: {detail[:200]}")

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Gemini image generation timed out (120s)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gemini image generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)[:200]}")


_WORKFLOW_DIR = Path(__file__).parent.parent.parent.parent / "data" / "workflows"


def _hydrate_workflow(workflow_template: dict, variables: dict) -> dict:
    """Replace {{placeholder}} variables in a workflow template.

    Handles string values (prompt, checkpoint) and converts width/height to ints.
    Also randomises seed if it's 0.
    """
    raw = json.dumps(workflow_template)

    # Replace string placeholders
    for key, value in variables.items():
        raw = raw.replace("{{" + key + "}}", str(value))

    hydrated = json.loads(raw)

    # Walk the tree and fix types
    for node_id, node in hydrated.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        # Ints: width, height, batch_size, steps
        for field in ("width", "height", "batch_size", "steps"):
            if field in inputs and isinstance(inputs[field], str):
                try:
                    inputs[field] = int(inputs[field])
                except ValueError:
                    pass
        # Floats: cfg, denoise, strength_model, strength_clip
        for field in ("cfg", "denoise", "strength_model", "strength_clip"):
            if field in inputs and isinstance(inputs[field], str):
                try:
                    inputs[field] = float(inputs[field])
                except ValueError:
                    pass
        # Seed: randomize if 0
        if "seed" in inputs:
            if inputs["seed"] == 0 or inputs["seed"] == "0":
                inputs["seed"] = random.randint(1, 2**32 - 1)
            elif isinstance(inputs["seed"], str):
                try:
                    inputs["seed"] = int(inputs["seed"])
                except ValueError:
                    inputs["seed"] = random.randint(1, 2**32 - 1)

    return hydrated


def _inject_prompt_into_workflow(workflow: dict, prompt: str) -> dict:
    """Inject the user's prompt into a workflow's primary positive CLIPTextEncode node.

    Strategy — we trust the workflow completely for everything else (checkpoint,
    LoRA, size, negative prompt, sampler, etc.) and ONLY replace the text in:
      1. Any CLIPTextEncode node containing the literal string "{{prompt}}"
      2. OR: the positive conditioning input to the KSampler if no placeholder found
    """
    # First pass: find {{prompt}} placeholder and replace it
    raw = json.dumps(workflow)
    if "{{prompt}}" in raw:
        safe_prompt = json.dumps(prompt)[1:-1]  # JSON-escape the prompt string
        raw = raw.replace("{{prompt}}", safe_prompt)
        workflow = json.loads(raw)
        # Also randomize any {{seed}} = 0 patterns that may still be strings
        for node in workflow.values():
            if isinstance(node, dict):
                inputs = node.get("inputs", {})
                if "seed" in inputs and (inputs["seed"] == 0 or inputs["seed"] == "0"):
                    inputs["seed"] = random.randint(1, 2**32 - 1)
        return workflow

    # Second pass: no placeholder — find the positive-conditioning text node.
    # KSampler/KSamplerAdvanced has a "positive" input pointing to a CLIPTextEncode.
    # We follow that link and replace its "text" field.
    positive_text_node_id = None
    for nid, node in workflow.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") in ("KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"):
            positive_ref = node.get("inputs", {}).get("positive")
            if isinstance(positive_ref, list) and len(positive_ref) == 2:
                positive_text_node_id = str(positive_ref[0])
                break

    if positive_text_node_id and positive_text_node_id in workflow:
        target = workflow[positive_text_node_id]
        if isinstance(target, dict) and "inputs" in target and "text" in target["inputs"]:
            target["inputs"]["text"] = prompt
            logger.info(f"Injected prompt into positive text node {positive_text_node_id}")
        else:
            logger.warning(f"Positive node {positive_text_node_id} has no 'text' input")
    else:
        # Last resort: replace text in the first CLIPTextEncode node found
        for nid, node in workflow.items():
            if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
                node.get("inputs", {})["text"] = prompt
                logger.info(f"Injected prompt into first CLIPTextEncode node {nid} (fallback)")
                break

    # Randomize seed if it's 0
    for node in workflow.values():
        if isinstance(node, dict):
            inputs = node.get("inputs", {})
            if "seed" in inputs and (inputs["seed"] == 0 or inputs["seed"] == "0"):
                inputs["seed"] = random.randint(1, 2**32 - 1)

    return workflow


# Friendly labels for common ComfyUI node types — used in progress messages
_NODE_LABELS = {
    "CheckpointLoaderSimple": "Loading checkpoint",
    "UNETLoader": "Loading UNET model",
    "DualCLIPLoader": "Loading CLIP models",
    "CLIPLoader": "Loading CLIP",
    "VAELoader": "Loading VAE",
    "LoraLoader": "Applying LoRA",
    "LoraLoaderModelOnly": "Applying LoRA",
    "CLIPTextEncode": "Encoding prompt",
    "EmptyLatentImage": "Preparing canvas",
    "EmptySD3LatentImage": "Preparing canvas",
    "KSampler": "Sampling",
    "KSamplerAdvanced": "Sampling",
    "SamplerCustom": "Sampling",
    "VAEDecode": "Decoding image",
    "SaveImage": "Saving image",
    "PreviewImage": "Finalizing preview",
    "UnetLoaderGGUF": "Loading GGUF model",
}


def _friendly_node_label(class_type: str) -> str:
    """Return a human-friendly label for a ComfyUI node class."""
    if class_type in _NODE_LABELS:
        return _NODE_LABELS[class_type]
    # Fall back to a prettified class name
    return class_type.replace("_", " ")


async def _stream_comfyui_progress(
    comfyui_url: str,
    prompt_id: str,
    workflow: dict,
    progress_cb,
    stop_event: "asyncio.Event",
):
    """Subscribe to ComfyUI's WebSocket and forward progress updates.

    ComfyUI emits events:
      - executing {node, prompt_id}         → a node is starting
      - progress  {value, max, node}        → sampler step progress
      - executed  {node, output, prompt_id} → node finished
    """
    import websockets  # pyright: ignore
    ws_url = comfyui_url.replace("http://", "ws://").replace("https://", "wss://").rstrip("/") + "/ws"
    try:
        async with websockets.connect(ws_url, ping_interval=20) as ws:
            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
                if not isinstance(raw, str):
                    continue  # binary preview frames — ignore
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                msg_type = msg.get("type")
                data = msg.get("data", {})
                if data.get("prompt_id") and data.get("prompt_id") != prompt_id:
                    continue  # not our job

                if msg_type == "executing":
                    node_id = data.get("node")
                    if node_id is None:
                        continue  # execution finished
                    node = workflow.get(str(node_id), {})
                    label = _friendly_node_label(node.get("class_type", ""))
                    try:
                        await progress_cb(f"{label}…", None)
                    except Exception:
                        pass
                elif msg_type == "progress":
                    val = data.get("value", 0)
                    mx = data.get("max", 1) or 1
                    percent = int((val / mx) * 100) if mx else 0
                    try:
                        await progress_cb(f"Sampling step {val}/{mx}", percent)
                    except Exception:
                        pass
                elif msg_type == "execution_success":
                    try:
                        await progress_cb("Finalizing image…", 100)
                    except Exception:
                        pass
                    break
                elif msg_type == "execution_error":
                    break
    except Exception as e:
        logger.debug(f"ComfyUI WS stream ended: {e}")


async def generate_with_comfyui(
    prompt: str,
    comfyui_url: str,
    workflow_id: str = None,
    comfyui_dir: str = "",
    progress_cb=None,  # async callable: progress_cb(message: str, percent: int)
    # Legacy params kept for backward compat with callers — IGNORED for ComfyUI.
    # Workflow is treated as-saved: checkpoint, LoRA, size, negative prompt,
    # sampler, steps all come from the workflow JSON itself.
    size: str = "1024x1024",
    negative_prompt: str = None,
    checkpoint: str = None,
    lora: str = None,
    lora_strength: float = 1.0,
    poll_timeout_seconds: Optional[int] = None,
) -> dict:
    """Generate an image using ComfyUI.

    User picks a pre-saved workflow + types a prompt. Everything else
    (checkpoint, LoRA, size, negative prompt, sampler, steps) comes from the
    workflow as it was saved in ComfyUI. To change those, edit the workflow
    in ComfyUI's editor and save it.
    """
    effective_workflow_id = workflow_id or "sdxl-standard"
    logger.info(f"ComfyUI gen: workflow={effective_workflow_id}, prompt={prompt[:60]}…")

    # Load the workflow file
    template_path = find_workflow_path(effective_workflow_id, comfyui_dir)
    if not template_path:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{effective_workflow_id}' not found. Save it in ComfyUI first or check the workflow list.",
        )

    try:
        raw_text = template_path.read_text(encoding="utf-8-sig")  # handle BOM
        template_data = json.loads(raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load workflow: {e}")

    # Extract the API-format workflow nodes
    workflow_json = template_data.get("workflow", template_data)
    is_api_format = workflow_json and isinstance(workflow_json, dict) and any(
        isinstance(v, dict) and "class_type" in v for v in workflow_json.values()
    )

    # If it's ComfyUI editor format (nodes/links arrays), convert it.
    # Fetch ComfyUI's own node schema so the converter knows which widget
    # values map to which input names for each node class.
    if not is_api_format and isinstance(template_data, dict) and "nodes" in template_data:
        logger.info(f"Converting editor-format workflow: {template_path.name}")
        node_schema = await _fetch_object_info_schema(comfyui_url)
        workflow_json = _convert_editor_to_api(template_data, node_schema=node_schema)
        if not workflow_json:
            raise HTTPException(
                status_code=400,
                detail=f"Workflow '{effective_workflow_id}' has no output nodes. "
                       f"Add a SaveImage/PreviewImage node in ComfyUI and save the workflow.",
            )

    if not workflow_json or not any(
        isinstance(v, dict) and "class_type" in v for v in workflow_json.values()
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Workflow '{effective_workflow_id}' is not valid. "
                   f"Save it from ComfyUI's editor to generate a valid API-format file.",
        )

    # Inject ONLY the prompt — everything else is trusted from the workflow
    workflow = _inject_prompt_into_workflow(workflow_json, prompt)

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            # Queue the prompt
            queue_response = await client.post(
                f"{comfyui_url}/prompt",
                json={"prompt": workflow},
                headers={"Content-Type": "application/json"}
            )
            
            if queue_response.status_code != 200:
                error_msg = queue_response.text
                logger.error(f"ComfyUI rejected workflow (HTTP {queue_response.status_code}): {error_msg[:500]}")
                if "connection refused" in error_msg.lower():
                    raise HTTPException(
                        status_code=503,
                        detail="ComfyUI not running. Start ComfyUI at http://localhost:8188"
                    )
                raise HTTPException(
                    status_code=500,
                    detail=f"ComfyUI error: {error_msg[:300]}"
                )
            
            result = queue_response.json()
            prompt_id = result.get("prompt_id")

            if not prompt_id:
                raise HTTPException(
                    status_code=500,
                    detail="ComfyUI did not return a prompt ID"
                )

            # Start WebSocket listener for live progress (if callback provided)
            ws_stop_event = asyncio.Event()
            ws_task = None
            if progress_cb is not None:
                ws_task = asyncio.create_task(
                    _stream_comfyui_progress(comfyui_url, prompt_id, workflow, progress_cb, ws_stop_event)
                )

            # Poll for completion — allow longer runs when ComfyUI is offloading
            # to system RAM under heavy workflows/masking.
            max_poll = _clamp_poll_timeout_seconds(poll_timeout_seconds, 1800)
            for attempt in range(max_poll):
                await asyncio.sleep(1)
                if attempt > 0 and attempt % 30 == 0:
                    logger.info(f"ComfyUI still generating… {attempt}s elapsed")
                
                history_response = await client.get(
                    f"{comfyui_url}/history/{prompt_id}"
                )
                
                if history_response.status_code == 200:
                    history = history_response.json()
                    if prompt_id in history:
                        entry = history[prompt_id]
                        status_info = entry.get("status", {})
                        status_str = status_info.get("status_str", "")

                        # Check for execution error
                        if status_str == "error":
                            msgs = status_info.get("messages", [])
                            err_detail = str(msgs) if msgs else "unknown error"
                            logger.error(f"ComfyUI execution failed: {err_detail[:300]}")
                            await _stop_comfyui_progress_task(ws_stop_event, ws_task)
                            raise HTTPException(status_code=500, detail=f"ComfyUI execution error: {err_detail[:300]}")

                        outputs = entry.get("outputs", {})
                        for node_id, node_output in outputs.items():
                            file_refs = _extract_comfyui_file_refs(node_output)
                            if file_refs:
                                for img in file_refs:
                                    filename = img.get("filename", "")
                                    subfolder = img.get("subfolder", "")
                                    img_type = img.get("type", "output")

                                    # Get the image
                                    view_url = f"{comfyui_url}/view"
                                    params = {
                                        "filename": filename,
                                        "subfolder": subfolder,
                                        "type": img_type
                                    }

                                    img_response = await client.get(view_url, params=params)

                                    if img_response.status_code == 200:
                                        image_bytes = img_response.content
                                        elapsed = attempt + 1
                                        logger.info(f"ComfyUI generation complete in {elapsed}s, image: {filename}")
                                        await _stop_comfyui_progress_task(ws_stop_event, ws_task)
                                        return {
                                            "base64": base64.b64encode(image_bytes).decode('utf-8'),
                                            "revised_prompt": prompt
                                        }

            # Timed out — stop the WS streamer
            await _stop_comfyui_progress_task(ws_stop_event, ws_task)
            await _cancel_comfyui_prompt(client, comfyui_url, prompt_id)
            raise HTTPException(
                status_code=504,
                detail=f"ComfyUI generation timed out after {max_poll // 60} minutes"
            )
            
    except asyncio.CancelledError:
        try:
            await _stop_comfyui_progress_task(ws_stop_event, ws_task)
            if 'client' in locals() and 'prompt_id' in locals() and prompt_id:
                await _cancel_comfyui_prompt(client, comfyui_url, prompt_id)
        finally:
            raise
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="ComfyUI connection timed out"
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"ComfyUI not reachable at {comfyui_url}. Ensure ComfyUI is running."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ComfyUI generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"ComfyUI generation failed: {str(e)}"
        )


def _convert_txt2img_to_img2img(workflow: dict, uploaded_image_name: str, denoise: float = 0.65) -> dict:
    """Auto-convert a txt2img workflow to img2img by injecting LoadImage + VAEEncode.

    Looks for EmptyLatentImage in the workflow and reroutes the KSampler's
    latent_image input through a new LoadImage → VAEEncode chain that uses
    the uploaded source image. Also lowers the KSampler's denoise strength
    so it's a variation, not a full regeneration.

    If the workflow already has a LoadImage node (i.e., it's already img2img),
    this function just updates the image filename and returns it unchanged
    structurally.
    """
    # Case 1: workflow is already img2img — update existing LoadImage
    load_image_nodes = [
        nid for nid, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") == "LoadImage"
    ]
    if load_image_nodes:
        for nid in load_image_nodes:
            workflow[nid].setdefault("inputs", {})["image"] = uploaded_image_name
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") in ("KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"):
                inputs = node.setdefault("inputs", {})
                if "denoise" in inputs:
                    inputs["denoise"] = denoise
        logger.info(f"Workflow has LoadImage — using as-is with uploaded image")
        return workflow

    # Case 2: txt2img workflow — find EmptyLatentImage to replace
    empty_latent_id = None
    for nid, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") in (
            "EmptyLatentImage", "EmptySD3LatentImage", "EmptyHunyuanLatentVideo"
        ):
            empty_latent_id = nid
            break

    if not empty_latent_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot convert workflow to img2img — no EmptyLatentImage node found to replace"
        )

    # Find the VAE source (from CheckpointLoaderSimple's 3rd output, or dedicated VAELoader)
    vae_source = None
    for nid, node in workflow.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        if ct in ("CheckpointLoaderSimple", "CheckpointLoader", "unCLIPCheckpointLoader"):
            vae_source = [nid, 2]  # index 2 = VAE
            break
        if ct == "VAELoader":
            vae_source = [nid, 0]
            break
    if not vae_source:
        raise HTTPException(
            status_code=400,
            detail="Cannot convert workflow to img2img — no CheckpointLoader or VAELoader found"
        )

    # Generate new node IDs (max existing + 1, +2)
    numeric_ids = [int(k) for k in workflow.keys() if str(k).isdigit()]
    base_id = max(numeric_ids) if numeric_ids else 100
    load_image_id = str(base_id + 1)
    vae_encode_id = str(base_id + 2)

    # Inject LoadImage + VAEEncode
    workflow[load_image_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": uploaded_image_name}
    }
    workflow[vae_encode_id] = {
        "class_type": "VAEEncode",
        "inputs": {"pixels": [load_image_id, 0], "vae": vae_source}
    }

    # Rewire every KSampler's latent_image input from EmptyLatentImage → VAEEncode
    # Also lower denoise for true variation behavior
    rewired = 0
    for nid, node in workflow.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") in ("KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"):
            inputs = node.setdefault("inputs", {})
            latent_ref = inputs.get("latent_image")
            if isinstance(latent_ref, list) and len(latent_ref) == 2 and str(latent_ref[0]) == str(empty_latent_id):
                inputs["latent_image"] = [vae_encode_id, 0]
                # Only set denoise if the node accepts it (KSampler does, KSamplerAdvanced does not — it uses start_at_step)
                if node.get("class_type") == "KSampler":
                    inputs["denoise"] = denoise
                rewired += 1

    if rewired == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot convert workflow — no KSampler referenced EmptyLatentImage node '{empty_latent_id}'"
        )

    logger.info(f"Auto-converted txt2img → img2img: injected LoadImage={load_image_id}, VAEEncode={vae_encode_id}, rewired {rewired} sampler(s), denoise={denoise}")
    return workflow


def _resolve_denoise(value: Optional[float], default: float) -> float:
    """Validate an optional denoise value and fall back to a default."""
    if value is None:
        return default
    denoise = float(value)
    if denoise < 0.0 or denoise > 1.0:
        raise HTTPException(status_code=422, detail="denoise must be between 0.0 and 1.0")
    return denoise


def _as_bool(raw: Optional[str]) -> bool:
    """Parse truthy app setting values like 1/true/yes/on."""
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _clamp_poll_timeout_seconds(value: Optional[int], default: int) -> int:
    """Clamp ComfyUI poll timeout between 60s and 6h, with fallback default."""
    if value is None:
        return default
    try:
        timeout = int(value)
    except Exception:
        return default
    if timeout < 60:
        return 60
    if timeout > 21600:
        return 21600
    return timeout


def _resolve_img2img_poll_timeout_seconds(
    poll_timeout_seconds: Optional[int],
    has_mask: bool,
) -> int:
    """Resolve img2img poll timeout, extending masked runs by default.

    Masked inpaint workflows (especially FLUX + multi-region masks) can run
    significantly longer than plain img2img and may exceed even 90 minutes on
    memory-constrained systems:
      - Sampling alone: 28 steps × ~95s = ~44 min
      - VAE decode (heavily offloaded): can add another 20-30 min
      - Total observed: up to ~1h45m on a single masked FLUX run

    Enforce a 3-hour minimum for masked runs so VAE decode is never cut off.
    Keep non-masked behavior unchanged.
    """
    timeout = _clamp_poll_timeout_seconds(poll_timeout_seconds, 1800)
    if has_mask and timeout < 10800:
        return 10800
    return timeout


async def _get_comfyui_poll_timeout_seconds(
    db: Optional[AsyncSession] = None,
    default_seconds: int = 1800,
    long_load_seconds: int = 10800,
) -> int:
    """Resolve ComfyUI poll timeout from explicit value or long-load mode toggle."""
    timeout_raw = await get_setting("comfyui_poll_timeout_seconds", db)
    if str(timeout_raw or "").strip():
        return _clamp_poll_timeout_seconds(timeout_raw, default_seconds)

    long_mode_raw = await get_setting("comfyui_long_load_mode", db)
    if _as_bool(long_mode_raw):
        return _clamp_poll_timeout_seconds(long_load_seconds, long_load_seconds)

    return _clamp_poll_timeout_seconds(default_seconds, default_seconds)


def _resolve_mask_grow(value: Optional[int], default: int = 8) -> int:
    """Validate an optional mask grow value in pixels."""
    if value is None:
        return default
    grow = int(value)
    if grow < 0 or grow > 128:
        raise HTTPException(status_code=422, detail="mask_grow must be between 0 and 128")
    return grow


def _resolve_mask_feather(value: Optional[float], default: float = 6.0) -> float:
    """Validate an optional mask feather value."""
    if value is None:
        return default
    feather = float(value)
    if feather < 0.0 or feather > 64.0:
        raise HTTPException(status_code=422, detail="mask_feather must be between 0.0 and 64.0")
    return feather


def _mask_blur_kernel(mask_feather: float) -> int:
    """Map a feather radius to an odd blur kernel size."""
    if mask_feather <= 0:
        return 0
    kernel = int(round(mask_feather * 2)) + 1
    return max(3, min(101, kernel if kernel % 2 == 1 else kernel + 1))


def _find_vae_source(workflow: dict) -> list:
    """Locate a VAE output reference inside a workflow."""
    for nid, node in workflow.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        if ct in ("CheckpointLoaderSimple", "CheckpointLoader", "unCLIPCheckpointLoader"):
            return [nid, 2]
        if ct == "VAELoader":
            return [nid, 0]
    raise HTTPException(
        status_code=400,
        detail="Cannot prepare ComfyUI workflow — no CheckpointLoader or VAELoader found",
    )


def _next_node_id(workflow: dict) -> int:
    """Return the next numeric node id for an API-format ComfyUI workflow."""
    numeric_ids = [int(k) for k in workflow.keys() if str(k).isdigit()]
    return (max(numeric_ids) if numeric_ids else 100) + 1


def _replace_node_reference(
    workflow: dict,
    old_ref: list,
    new_ref: list,
    input_names: tuple[str, ...] = ("image", "images"),
) -> int:
    """Replace matching workflow node references on common image-style inputs."""
    rewired = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for input_name in input_names:
            value = inputs.get(input_name)
            if value == old_ref:
                inputs[input_name] = new_ref
                rewired += 1
    return rewired


def _convert_workflow_to_masked_inpaint(
    workflow: dict,
    uploaded_image_name: str,
    uploaded_mask_name: str,
    denoise: float = 0.45,
    node_schema: Optional[dict[str, list[str]]] = None,
    mask_grow: int = 8,
    mask_feather: float = 6.0,
) -> dict:
    """Convert or adapt a workflow so masked edits only replace editable regions.

    The incoming mask is expected to use white for editable regions and black
    for protected regions. The workflow is run as img2img, then only the
    editable region is composited back over the original image.
    """
    workflow = _convert_txt2img_to_img2img(workflow, uploaded_image_name, denoise=denoise)
    node_schema = node_schema or {}

    load_image_nodes = [
        nid for nid, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") == "LoadImage"
    ]
    if not load_image_nodes:
        raise HTTPException(
            status_code=400,
            detail="Cannot prepare masked edit workflow — no LoadImage node found after img2img conversion",
        )

    for nid in load_image_nodes:
        workflow[nid].setdefault("inputs", {})["image"] = uploaded_image_name
    load_image_id = load_image_nodes[0]

    load_mask_nodes = [
        nid for nid, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") == "LoadImageMask"
    ]

    if load_mask_nodes:
        for nid in load_mask_nodes:
            inputs = workflow[nid].setdefault("inputs", {})
            inputs["image"] = uploaded_mask_name
            inputs.setdefault("channel", "red")
        load_mask_id = load_mask_nodes[0]
    else:
        load_mask_id = str(_next_node_id(workflow))
        workflow[load_mask_id] = {
            "class_type": "LoadImageMask",
            "inputs": {"image": uploaded_mask_name, "channel": "red"},
        }

    sampler_ids: list[str] = []
    rewired = 0
    for nid, node in workflow.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") in ("KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"):
            inputs = node.setdefault("inputs", {})
            if "denoise" in inputs:
                inputs["denoise"] = denoise
            sampler_ids.append(nid)
            rewired += 1

    if rewired == 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot convert workflow to masked inpaint — no sampler nodes were found",
        )

    composite_id = None
    composite_mask_ref = [load_mask_id, 0]

    if "GrowMask" in node_schema and mask_grow > 0:
        grow_mask_id = str(_next_node_id(workflow))
        workflow[grow_mask_id] = {
            "class_type": "GrowMask",
            "inputs": {
                "mask": [load_mask_id, 0],
                "expand": mask_grow,
                "tapered_corners": True,
            },
        }
        composite_mask_ref = [grow_mask_id, 0]

    if "ImpactGaussianBlurMask" in node_schema and mask_feather > 0:
        kernel_size = _mask_blur_kernel(mask_feather)
        blur_mask_id = str(_next_node_id(workflow))
        workflow[blur_mask_id] = {
            "class_type": "ImpactGaussianBlurMask",
            "inputs": {
                "mask": composite_mask_ref,
                "kernel_size": kernel_size,
                "sigma": mask_feather,
            },
        }
        composite_mask_ref = [blur_mask_id, 0]

    output_rewired = 0
    if "ImageCompositeMasked" in node_schema and sampler_ids:
        primary_sampler_id = sampler_ids[0]
        decode_id = next(
            (
                nid
                for nid, node in workflow.items()
                if isinstance(node, dict)
                and node.get("class_type") == "VAEDecode"
                and node.get("inputs", {}).get("samples") == [primary_sampler_id, 0]
            ),
            None,
        )

        if not decode_id:
            decode_id = str(_next_node_id(workflow))
            workflow[decode_id] = {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": [primary_sampler_id, 0],
                    "vae": vae_source,
                },
            }

        composite_id = str(_next_node_id(workflow))
        workflow[composite_id] = {
            "class_type": "ImageCompositeMasked",
            "inputs": {
                "destination": [load_image_id, 0],
                "source": [decode_id, 0],
                "x": 0,
                "y": 0,
                "resize_source": False,
                "mask": composite_mask_ref,
            },
        }

        output_rewired += _replace_node_reference(workflow, [decode_id, 0], [composite_id, 0])
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") not in ("SaveImage", "PreviewImage"):
                continue
            inputs = node.setdefault("inputs", {})
            if "images" in inputs:
                inputs["images"] = [composite_id, 0]
                output_rewired += 1
            elif "image" in inputs:
                inputs["image"] = [composite_id, 0]
                output_rewired += 1

    logger.info(
        "Prepared masked composite workflow: LoadImage=%s LoadImageMask=%s samplers=%s denoise=%s mask_grow=%s mask_feather=%s composite=%s output_rewired=%s",
        load_image_id,
        load_mask_id,
        rewired,
        denoise,
        mask_grow,
        mask_feather,
        composite_id,
        output_rewired,
    )
    return workflow


def _extension_for_mime_type(mime_type: str) -> str:
    """Return a sensible file extension for an image MIME type."""
    normalized = (mime_type or "image/png").lower().strip()
    if normalized == "image/jpeg":
        return "jpg"
    if normalized.startswith("image/"):
        return normalized.split("/", 1)[1]
    return "png"


def _ensure_comfyui_png_source(source_mime: str, operation: str) -> None:
    """Reject non-PNG source images for ComfyUI img2img-style operations."""
    normalized = (source_mime or "").lower().strip()
    if normalized != "image/png":
        raise HTTPException(
            status_code=400,
            detail=(
                f"ComfyUI currently requires a PNG source image for {operation}. "
                f"This image is {normalized or 'an unknown format'}. Re-upload or convert it to PNG, "
                f"or use Gemini for this request."
            ),
        )


async def _upload_image_to_comfyui(
    source_bytes: bytes,
    comfyui_url: str,
    filename: str = "devforgeai_variation.png",
    mime_type: str = "image/png",
) -> str:
    """Upload raw image bytes to ComfyUI's /upload/image endpoint. Returns the name ComfyUI assigns."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        files = {"image": (filename, source_bytes, mime_type)}
        data = {"overwrite": "true"}
        resp = await client.post(f"{comfyui_url}/upload/image", files=files, data=data)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"ComfyUI rejected image upload: {resp.text[:200]}"
            )
        body = resp.json()
        # ComfyUI returns {"name": "...", "subfolder": "", "type": "input"}
        return body.get("name") or filename


async def generate_img2img_with_comfyui(
    source_bytes: bytes,
    prompt: str,
    comfyui_url: str,
    comfyui_dir: str = "",
    workflow_id: str = "sdxl-img2img",
    source_mime: str = "image/png",
    mask_bytes: Optional[bytes] = None,
    mask_mime: str = "image/png",
    denoise: float = 0.65,
    mask_grow: int = 8,
    mask_feather: float = 6.0,
    progress_cb=None,
    poll_timeout_seconds: Optional[int] = None,
) -> dict:
    """Run an img2img variation via ComfyUI.

    Uploads the source image to ComfyUI's input folder, loads the chosen
    workflow template, and either:
      - uses it as-is if it already has a LoadImage node (true img2img workflow)
      - auto-converts it to img2img by injecting LoadImage + VAEEncode nodes
        if it's a txt2img workflow

    This means ANY workflow (including custom/uncensored ones) can be used
    for variations.
    """
    logger.info(f"ComfyUI img2img: workflow={workflow_id}, source_bytes={len(source_bytes)}, prompt={prompt[:60]}…")

    # 1. Upload source image to ComfyUI
    source_ext = _extension_for_mime_type(source_mime)
    uploaded_name = await _upload_image_to_comfyui(
        source_bytes,
        comfyui_url,
        filename=f"devforgeai_variation_{uuid.uuid4().hex}.{source_ext}",
        mime_type=source_mime,
    )
    logger.info(f"Uploaded source image to ComfyUI as: {uploaded_name}")

    uploaded_mask_name = None
    if mask_bytes is not None:
        uploaded_mask_name = await _upload_image_to_comfyui(
            mask_bytes,
            comfyui_url,
            filename=f"devforgeai_mask_{uuid.uuid4().hex}.png",
            mime_type=mask_mime,
        )
        logger.info(f"Uploaded mask image to ComfyUI as: {uploaded_mask_name}")

    # 2. Load the workflow template
    template_path = find_workflow_path(workflow_id, comfyui_dir)
    if not template_path:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{workflow_id}' not found. Expected at data/workflows/{workflow_id}.json"
        )

    try:
        raw_text = template_path.read_text(encoding="utf-8-sig")
        template_data = json.loads(raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load workflow: {e}")

    workflow_json = template_data.get("workflow", template_data)
    node_schema: dict[str, list[str]] = {}
    is_api_format = workflow_json and isinstance(workflow_json, dict) and any(
        isinstance(v, dict) and "class_type" in v for v in workflow_json.values()
    )

    # Convert ComfyUI editor format (nodes/links arrays) to API format if needed
    if not is_api_format and isinstance(template_data, dict) and "nodes" in template_data:
        logger.info(f"Converting editor-format workflow to API format: {workflow_id}")
        node_schema = await _fetch_object_info_schema(comfyui_url)
        workflow_json = _convert_editor_to_api(template_data, node_schema=node_schema)
        if not workflow_json:
            raise HTTPException(
                status_code=400,
                detail=f"Workflow '{workflow_id}' has no output nodes. "
                       f"Add a SaveImage/PreviewImage node in ComfyUI and save the workflow."
            )
        is_api_format = True

    if not is_api_format:
        raise HTTPException(
            status_code=400,
            detail=f"Workflow '{workflow_id}' is not in API format and could not be auto-converted. "
                   f"In ComfyUI: open the workflow, click Workflow → Export (API Format), and save the resulting JSON to data/workflows/"
        )

    # 3. Hydrate the workflow's template placeholders (prompt, checkpoint, etc.)
    default_checkpoint = template_data.get("default_checkpoint", "sdxl.safetensors")
    variables = {
        "init_image": uploaded_name,
        "prompt": prompt or "high quality variation",
        "negative_prompt": "",
        "checkpoint": default_checkpoint,
        "width": 1024,
        "height": 1024,
    }
    workflow = _hydrate_workflow(workflow_json, variables)

    # 4. Ensure the workflow is img2img-capable. If it's txt2img, auto-convert
    #    it by injecting LoadImage + VAEEncode and rewiring KSamplers.
    if uploaded_mask_name:
        if not node_schema:
            node_schema = await _fetch_object_info_schema(comfyui_url)
        workflow = _convert_workflow_to_masked_inpaint(
            workflow,
            uploaded_name,
            uploaded_mask_name,
            denoise=denoise,
            node_schema=node_schema,
            mask_grow=mask_grow,
            mask_feather=mask_feather,
        )
    else:
        workflow = _convert_txt2img_to_img2img(workflow, uploaded_name, denoise=denoise)

    # Always randomize sampler seeds for variations.
    # Reusing the same source filename + seed can cause ComfyUI to serve a
    # cached success with empty outputs, which leaves the frontend waiting even
    # though the asset appears inside ComfyUI.
    for node in workflow.values():
        if isinstance(node, dict) and node.get("class_type") in ("KSampler", "KSamplerAdvanced"):
            inputs = node.get("inputs", {})
            inputs["seed"] = random.randint(1, 2**32 - 1)

    # 4. Queue + poll the workflow
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            queue_resp = await client.post(
                f"{comfyui_url}/prompt",
                json={"prompt": workflow},
                headers={"Content-Type": "application/json"}
            )
            if queue_resp.status_code != 200:
                # Log the full workflow so we can diagnose
                logger.error(f"ComfyUI rejected workflow {workflow_id}. Response: {queue_resp.text[:800]}")
                logger.error(f"Workflow sent: {json.dumps(workflow)[:2000]}")
                raise HTTPException(
                    status_code=500,
                    detail=f"ComfyUI rejected '{workflow_id}' workflow: {queue_resp.text[:300]}"
                )
            prompt_id = queue_resp.json().get("prompt_id")
            if not prompt_id:
                raise HTTPException(status_code=500, detail="ComfyUI did not return a prompt ID")
            logger.info(f"ComfyUI queued img2img prompt {prompt_id} (workflow={workflow_id})")

            ws_stop_event = asyncio.Event()
            ws_task = None
            if progress_cb is not None:
                ws_task = asyncio.create_task(
                    _stream_comfyui_progress(comfyui_url, prompt_id, workflow, progress_cb, ws_stop_event)
                )

            # Poll history. Masked img2img can legitimately run much longer
            # than plain img2img/txt2img on local ComfyUI.
            max_poll = _resolve_img2img_poll_timeout_seconds(
                poll_timeout_seconds,
                has_mask=uploaded_mask_name is not None,
            )
            for attempt in range(max_poll):
                await asyncio.sleep(1)
                if attempt > 0 and attempt % 30 == 0:
                    logger.info(f"ComfyUI img2img still running… {attempt}s elapsed (workflow={workflow_id}, prompt_id={prompt_id})")
                hist_resp = await client.get(f"{comfyui_url}/history/{prompt_id}")
                if hist_resp.status_code != 200:
                    continue
                history = hist_resp.json()
                if prompt_id not in history:
                    continue
                entry = history[prompt_id]
                status_info = entry.get("status", {})
                if status_info.get("completed") and not entry.get("outputs"):
                    logger.warning(
                        "ComfyUI prompt %s completed with no outputs; workflow=%s",
                        prompt_id,
                        workflow_id,
                    )
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            f"ComfyUI marked workflow '{workflow_id}' complete but returned no output files. "
                            "This usually indicates a fully cached execution. Retry the variation to force a fresh output."
                        ),
                    )
                if status_info.get("status_str") == "error":
                    msgs = status_info.get("messages", [])
                    # ComfyUI messages often wrap the real error deep in structured data
                    # Try to extract the most useful part
                    err_summary = ""
                    for m in msgs:
                        if isinstance(m, list) and len(m) >= 2:
                            event, data = m[0], m[1]
                            if event in ("execution_error", "execution_interrupted"):
                                err_summary = f"{data.get('node_type', '?')}/{data.get('node_id', '?')}: {data.get('exception_message', '?')}"
                                break
                    err_detail = err_summary or str(msgs)[:300]
                    logger.error(f"ComfyUI execution failed for prompt {prompt_id}: {err_detail}")
                    await _stop_comfyui_progress_task(ws_stop_event, ws_task)
                    raise HTTPException(
                        status_code=500,
                        detail=f"ComfyUI workflow '{workflow_id}' failed: {err_detail}"
                    )
                outputs = entry.get("outputs", {})
                for node_id, node_output in outputs.items():
                    file_refs = _extract_comfyui_file_refs(node_output)
                    if file_refs:
                        for img in file_refs:
                            view_resp = await client.get(
                                f"{comfyui_url}/view",
                                params={
                                    "filename": img.get("filename", ""),
                                    "subfolder": img.get("subfolder", ""),
                                    "type": img.get("type", "output"),
                                }
                            )
                            if view_resp.status_code == 200:
                                elapsed = attempt + 1
                                logger.info(f"ComfyUI img2img complete in {elapsed}s, image: {img.get('filename', '')}")
                                await _stop_comfyui_progress_task(ws_stop_event, ws_task)
                                return {
                                    "base64": base64.b64encode(view_resp.content).decode(),
                                    "revised_prompt": None,
                                }
            await _stop_comfyui_progress_task(ws_stop_event, ws_task)
            await _cancel_comfyui_prompt(client, comfyui_url, prompt_id)
            raise HTTPException(
                status_code=504,
                detail=f"ComfyUI img2img timed out after {max_poll // 60} minutes"
            )
    except asyncio.CancelledError:
        try:
            await _stop_comfyui_progress_task(ws_stop_event, ws_task)
            if 'client' in locals() and 'prompt_id' in locals() and prompt_id:
                await _cancel_comfyui_prompt(client, comfyui_url, prompt_id)
        finally:
            raise
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail=f"ComfyUI not reachable at {comfyui_url}")


@router.post("/generations", response_model=ImageListResponse)
async def generate_image(
    request: ImageGenerationRequest,
    db: AsyncSession = Depends(get_db)
):
    """Generate one or more images using the specified model."""
    
    images = []
    
    for i in range(request.num_variations):
        try:
            if request.model == "gemini-imagen":
                api_key = os.environ.get('GEMINI_API_KEY') or getattr(settings, 'gemini_api_key', None)
                if not api_key:
                    raise HTTPException(
                        status_code=500,
                        detail="GEMINI_API_KEY not configured. Add it to .env"
                    )
                result = await generate_with_gemini_imagen(
                    request.prompt, 
                    api_key, 
                    request.size
                )
                
            elif request.model == "comfyui-local":
                configured_comfyui_url = await get_setting("comfyui_url", db)
                comfyui_dir = await get_setting("comfyui_dir", db)

                # Try ComfyUI; fall back to Gemini on any failure (unreachable, timeout, error)
                comfyui_failed = False
                comfyui_error = ""
                try:
                    active_comfyui_url = await _resolve_comfyui_endpoint(configured_comfyui_url)
                    if not active_comfyui_url:
                        raise Exception(
                            f"ComfyUI not reachable at any configured URL: {configured_comfyui_url}"
                        )
                    result = await generate_with_comfyui(
                        prompt=request.prompt,
                        comfyui_url=active_comfyui_url,
                        workflow_id=request.workflow_id,
                        comfyui_dir=comfyui_dir,
                        poll_timeout_seconds=await _get_comfyui_poll_timeout_seconds(db),
                    )
                except Exception as comfy_err:
                    comfyui_failed = True
                    comfyui_error = getattr(comfy_err, 'detail', str(comfy_err))
                    logger.error(f"ComfyUI generation failed: {comfyui_error}")

                if comfyui_failed:
                    api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or getattr(settings, 'gemini_api_key', None) or getattr(settings, 'google_api_key', None)
                    if not api_key:
                        raise HTTPException(
                            status_code=503,
                            detail=f"ComfyUI failed ({comfyui_error}) and no Gemini API key configured for fallback."
                        )
                    result = await generate_with_gemini_imagen(request.prompt, api_key, request.size)
                    request.model = "gemini-imagen"

            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Model '{request.model}' does not support image generation. Use 'gemini-imagen' or 'comfyui-local'"
                )
            
            # Store image
            image_id = str(uuid.uuid4())
            IMAGE_STORAGE[image_id] = {
                "base64": result["base64"],
                "prompt": request.prompt,
                "revised_prompt": result.get("revised_prompt"),
                "format": request.format,
                "size": request.size,
                "model": request.model,
                "negative_prompt": request.negative_prompt,
                "workflow_id": request.workflow_id,
                "checkpoint": request.checkpoint,
                "lora": request.lora,
                "lora_strength": request.lora_strength,
            }
            
            # Parse size
            width, height = map(int, request.size.split('x'))
            
            images.append(ImageResponse(
                id=image_id,
                url=f"/v1/images/{image_id}",
                revised_prompt=result.get("revised_prompt"),
                width=width,
                height=height,
                format=request.format
            ))
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Image generation failed: {str(e)}"
            )
    
    return ImageListResponse(data=images, total=len(images))


@router.get("/models/available")
async def list_image_models(db: AsyncSession = Depends(get_db)):
    """List image generation backends available for generation + variations."""
    comfyui_url = await _get_running_comfyui_url(db, timeout=2.5)
    gemini_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or getattr(settings, "gemini_api_key", None)
        or getattr(settings, "google_api_key", None)
    )
    backends = [
        {
            "id": "gemini-imagen",
            "name": "Gemini (Imagen / Nano Banana)",
            "requires": "GEMINI_API_KEY",
            "available": bool(gemini_key),
            "description": "Fast cloud generation via Google",
        },
        {
            "id": "comfyui-local",
            "name": "ComfyUI (Local)",
            "requires": "ComfyUI running on localhost",
            "available": bool(comfyui_url),
            "description": "Local SDXL/FLUX workflows",
        },
    ]
    return {"data": backends}


@router.get("/{image_id}")
async def get_image(image_id: str):
    """Retrieve a generated image by ID."""
    
    if image_id not in IMAGE_STORAGE:
        raise HTTPException(
            status_code=404,
            detail="Image not found"
        )
    
    image_data = IMAGE_STORAGE[image_id]
    b64 = image_data.get("base64") or _load_image_base64(image_id, image_data.get("format", "png"))
    if not b64:
        raise HTTPException(status_code=404, detail="Image file not found on disk")
    image_bytes = base64.b64decode(b64)

    # Determine media type
    media_type = f"image/{image_data['format']}"

    return Response(
        content=image_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{image_id}.{image_data["format"]}"'
        }
    )


@router.get("/{image_id}/download")
async def download_image(image_id: str):
    """Download a generated image."""

    if image_id not in IMAGE_STORAGE:
        raise HTTPException(
            status_code=404,
            detail="Image not found"
        )

    image_data = IMAGE_STORAGE[image_id]
    b64 = image_data.get("base64") or _load_image_base64(image_id, image_data.get("format", "png"))
    if not b64:
        raise HTTPException(status_code=404, detail="Image file not found on disk")
    image_bytes = base64.b64decode(b64)
    media_type = f"image/{image_data['format']}"
    
    return Response(
        content=image_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="modelmesh-{image_id}.{image_data["format"]}"'
        }
    )


@router.delete("/{image_id}")
async def delete_image(image_id: str):
    """Delete a generated image — removes both the metadata and the file on disk."""

    # Find + delete the binary from data/images/ (this is the source of truth for the gallery)
    deleted_file = None
    for ext in ("png", "jpg", "jpeg", "webp", "gif"):
        p = _IMAGE_DIR / f"{image_id}.{ext}"
        if p.exists():
            try:
                p.unlink()
                deleted_file = p.name
                break
            except OSError as e:
                logger.warning(f"Could not delete {p}: {e}")

    # Remove from in-memory metadata + persist
    if image_id in IMAGE_STORAGE:
        del IMAGE_STORAGE[image_id]
        _save_image_storage(IMAGE_STORAGE)

    if not deleted_file and image_id not in IMAGE_STORAGE:
        raise HTTPException(status_code=404, detail="Image not found on disk or in metadata")

    return {"status": "deleted", "file": deleted_file}


@router.get("/")
async def list_images(
    limit: int = 50,
    offset: int = 0
):
    """List ALL images found in data/images, sorted newest-first by file mtime.

    Paginates (50 per page by default). Merges filesystem-discovered files with
    IMAGE_STORAGE metadata — any image file on disk gets returned even if its
    metadata is missing (stub response with disk-derived fields).
    """
    from datetime import datetime as _dt

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    # Scan directory for all image files
    disk_files = []
    try:
        for p in _IMAGE_DIR.iterdir():
            if not p.is_file():
                continue
            if p.name.startswith("_"):  # skip _meta.json etc
                continue
            if p.suffix.lower() not in _IMAGE_EXTS:
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            disk_files.append((p.stem, p.suffix.lstrip(".").lower(), mtime))
    except FileNotFoundError:
        disk_files = []

    # Sort newest first by mtime
    disk_files.sort(key=lambda t: t[2], reverse=True)
    total = len(disk_files)

    # Paginate
    page_slice = disk_files[offset:offset + limit]

    images = []
    for image_id, ext, mtime in page_slice:
        meta = IMAGE_STORAGE.get(image_id, {})
        try:
            size_str = meta.get("size", "0x0")
            width, height = map(int, size_str.split("x"))
        except (ValueError, AttributeError):
            width, height = 0, 0
        created_at = _dt.utcfromtimestamp(mtime).isoformat() + "Z"
        images.append(ImageResponse(
            id=image_id,
            url=f"/v1/img/{image_id}",
            revised_prompt=meta.get("revised_prompt"),
            width=width,
            height=height,
            format=meta.get("format") or ext,
            prompt=meta.get("prompt"),
            model=meta.get("model"),
            created_at=created_at,
            variation_of=meta.get("variation_of"),
        ))

    return ImageListResponse(data=images, total=total)




class ImageVariationRequest(BaseModel):
    size: Optional[str] = None      # If None, use original size
    format: Optional[str] = None    # If None, use original format
    model: Optional[str] = None     # "gemini-imagen" | "comfyui-local" — if None, use original's model
    prompt: Optional[str] = None    # Override prompt (for guided variations)
    workflow_id: Optional[str] = None  # ComfyUI workflow to use for img2img (defaults to "sdxl-img2img")
    denoise: Optional[float] = None
    mask_base64: Optional[str] = None
    mask_mime: str = "image/png"
    mask_grow: Optional[int] = None
    mask_feather: Optional[float] = None
    fast_mask: Optional[bool] = False  # If True, use optimized settings: denoise=0.4, mask_grow=0, mask_feather=0


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Return current status and progress for a background generation job."""
    job = _JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{image_id}/variations/async")
async def generate_variation_async(
    image_id: str,
    request: Optional[ImageVariationRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """Queue a variation as a background job. Returns job_id immediately."""
    original = IMAGE_STORAGE.get(image_id)
    if not original:
        found_on_disk = any(
            (_IMAGE_DIR / f"{image_id}.{ext}").exists()
            for ext in ("png", "jpg", "jpeg", "webp")
        )
        if not found_on_disk:
            raise HTTPException(status_code=404, detail="Original image not found")
        original = {"prompt": "", "model": "gemini-imagen", "size": "1024x1024", "format": "png"}

    comfyui_url_cfg = await get_setting("comfyui_url", db)
    comfyui_dir = await get_setting("comfyui_dir", db)
    poll_timeout = await _get_comfyui_poll_timeout_seconds(db)

    job_id = str(uuid.uuid4())
    _job_create(job_id, "variation", source_image_id=image_id)

    req_prompt = (request.prompt if request else None)
    req_model = (request.model if request else None)
    req_size = (request.size if request else None)
    req_format = (request.format if request else None)
    req_denoise = (request.denoise if request else None)
    req_mask_grow = (request.mask_grow if request else None)
    req_mask_feather = (request.mask_feather if request else None)
    req_fast_mask = (request.fast_mask if request else False)
    req_mask_base64 = (request.mask_base64 if request else None)
    req_mask_mime = (request.mask_mime if request else "image/png") or "image/png"
    req_workflow_id = (request.workflow_id if request else None)

    async def _run():
        try:
            _job_update(job_id, status="running", message="Starting…")
            prompt = req_prompt or original.get("prompt") or ""
            model = req_model or original.get("model") or "gemini-imagen"
            size = req_size or original.get("size", "1024x1024")
            fmt = req_format or original.get("format", "png")
            denoise = _resolve_denoise(req_denoise, 0.65)
            mask_grow = _resolve_mask_grow(req_mask_grow, 8)
            mask_feather = _resolve_mask_feather(req_mask_feather, 6.0)
            if req_fast_mask and req_mask_base64:
                denoise, mask_grow, mask_feather = 0.4, 0, 0.0

            mask_bytes = None
            if req_mask_base64:
                try:
                    mask_bytes = base64.b64decode(req_mask_base64)
                except Exception as exc:
                    _job_update(job_id, status="error", error=f"Invalid mask_base64: {exc}")
                    return

            source_bytes = None
            source_mime = "image/png"
            for ext in ("png", "jpg", "jpeg", "webp"):
                p = _IMAGE_DIR / f"{image_id}.{ext}"
                if p.exists():
                    source_bytes = p.read_bytes()
                    source_mime = "image/jpeg" if ext == "jpg" else f"image/{ext}"
                    break
            if not source_bytes:
                _job_update(job_id, status="error", error="Source image file not found on disk")
                return

            result = None
            if model == "gemini-imagen":
                api_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                           or getattr(settings, "gemini_api_key", None))
                if not api_key:
                    _job_update(job_id, status="error", error="GEMINI_API_KEY not configured")
                    return
                source_b64 = base64.b64encode(source_bytes).decode()
                if prompt.strip() and not prompt.startswith("Uploaded:"):
                    variation_prompt = (
                        f"Create a subtle variation of this image. Keep the overall "
                        f"subject, composition, and style the same, but introduce small "
                        f"differences in details, lighting, or pose. Original concept: {prompt}"
                    )
                else:
                    variation_prompt = (
                        "Create a subtle variation of this image. Keep the overall "
                        "subject, composition, and style the same, but introduce small "
                        "differences in details, lighting, or pose."
                    )
                result = await _gemini_image_edit(source_b64, source_mime, variation_prompt, api_key)
            elif model == "comfyui-local":
                _ensure_comfyui_png_source(source_mime, "variations")
                chosen_workflow = req_workflow_id or "sdxl-img2img"
                active_url = await _resolve_comfyui_endpoint(comfyui_url_cfg)
                if not active_url:
                    _job_update(job_id, status="error", error=f"ComfyUI not reachable at {comfyui_url_cfg}")
                    return
                progress_cb = _make_job_progress_cb(job_id)
                result = await generate_img2img_with_comfyui(
                    source_bytes=source_bytes,
                    prompt=prompt or "high quality variation",
                    comfyui_url=active_url,
                    comfyui_dir=comfyui_dir,
                    workflow_id=chosen_workflow,
                    source_mime=source_mime,
                    mask_bytes=mask_bytes,
                    mask_mime=req_mask_mime,
                    denoise=denoise,
                    mask_grow=mask_grow,
                    mask_feather=mask_feather,
                    poll_timeout_seconds=poll_timeout,
                    progress_cb=progress_cb,
                )
            else:
                _job_update(job_id, status="error", error=f"Model '{model}' does not support variations")
                return

            variation_id = str(uuid.uuid4())
            IMAGE_STORAGE[variation_id] = {
                "base64": result["base64"],
                "prompt": prompt,
                "revised_prompt": result.get("revised_prompt"),
                "format": fmt,
                "size": size,
                "model": model,
                "negative_prompt": original.get("negative_prompt"),
                "variation_of": image_id,
            }
            _store_image(variation_id, IMAGE_STORAGE[variation_id])
            _job_update(job_id, status="complete", result_id=variation_id, step=100, max_steps=100, message="Done")
        except Exception as exc:
            logger.error("Background variation job %s failed: %s", job_id, exc)
            _job_update(job_id, status="error", error=str(exc))

    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "pending"}


@router.post("/{image_id}/variations", response_model=ImageListResponse)
async def generate_variation(
    image_id: str,
    request: Optional[ImageVariationRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """Generate a variation of an existing image. User can choose which model to use."""

    # Try in-memory storage first, then fall back to disk metadata
    original = IMAGE_STORAGE.get(image_id)
    if not original:
        # Check if the image file exists on disk even without metadata
        found_on_disk = any(
            (_IMAGE_DIR / f"{image_id}.{ext}").exists()
            for ext in ("png", "jpg", "jpeg", "webp")
        )
        if not found_on_disk:
            raise HTTPException(status_code=404, detail="Original image not found")
        # Minimal stub for on-disk-only images
        original = {"prompt": "", "model": "gemini-imagen", "size": "1024x1024", "format": "png"}

    prompt = (request.prompt if request and request.prompt else original.get("prompt")) or ""
    negative_prompt = original.get("negative_prompt")
    # User-chosen model takes precedence over original's model
    model = (request.model if request and request.model else original.get("model")) or "gemini-imagen"
    size = request.size if request and request.size else original.get("size", "1024x1024")
    format = request.format if request and request.format else original.get("format", "png")
    denoise = _resolve_denoise(request.denoise if request else None, 0.65)
    mask_grow = _resolve_mask_grow(request.mask_grow if request else None, 8)
    mask_feather = _resolve_mask_feather(request.mask_feather if request else None, 6.0)
    
    # Apply fast_mask optimization if enabled (for CPU-constrained masked inpaint)
    if request and request.fast_mask and request.mask_base64:
        denoise = 0.4  # Reduced from 0.65; ~25% faster inference
        mask_grow = 0  # No mask expansion; saves CPU cycles
        mask_feather = 0.0  # No blur/feather; saves CPU cycles
        logger.info("Fast-mask mode enabled for variation: denoise=0.4, mask_grow=0, mask_feather=0.0")
    
    mask_bytes = None
    mask_mime = (request.mask_mime if request else None) or "image/png"
    if request and request.mask_base64:
        try:
            mask_bytes = base64.b64decode(request.mask_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid mask_base64 payload: {exc}")

    # Load the SOURCE IMAGE from disk — variations are img2img, they MUST use the original pixels
    source_bytes: Optional[bytes] = None
    source_mime = "image/png"
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = _IMAGE_DIR / f"{image_id}.{ext}"
        if p.exists():
            source_bytes = p.read_bytes()
            source_mime = f"image/{ext}" if ext != "jpg" else "image/jpeg"
            break
    if not source_bytes:
        raise HTTPException(status_code=404, detail="Source image file not found on disk — cannot do img2img variation")

    # Build the variation instruction. If we have the original prompt, incorporate it.
    # Otherwise, use a generic "make a variation" instruction.
    if prompt.strip() and not prompt.startswith("Uploaded:"):
        variation_prompt = f"Create a subtle variation of this image. Keep the overall subject, composition, and style the same, but introduce small differences in details, lighting, or pose. Original concept: {prompt}"
    else:
        variation_prompt = "Create a subtle variation of this image. Keep the overall subject, composition, and style the same, but introduce small differences in details, lighting, or pose."

    try:
        if model == "gemini-imagen":
            # Gemini multimodal img2img via its image-edit API
            api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or getattr(settings, 'gemini_api_key', None)
            if not api_key:
                raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")
            source_b64 = base64.b64encode(source_bytes).decode()
            result = await _gemini_image_edit(source_b64, source_mime, variation_prompt, api_key)

        elif model == "comfyui-local":
            # ComfyUI img2img — uploads source image and runs the chosen workflow.
            # NO silent fallback: if user picks ComfyUI and it fails, they see the real error.
            # (Fallback used to hide ComfyUI problems behind confusing Gemini errors.)
            _ensure_comfyui_png_source(source_mime, "variations")
            configured_comfyui_url = await get_setting("comfyui_url", db)
            comfyui_dir = await get_setting("comfyui_dir", db)
            chosen_workflow = (request.workflow_id if request and request.workflow_id else None) or "sdxl-img2img"

            active_comfyui_url = await _resolve_comfyui_endpoint(configured_comfyui_url)
            if not active_comfyui_url:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "ComfyUI not reachable at configured URL(s): "
                        f"{configured_comfyui_url}. Start ComfyUI, check the URL in Settings, "
                        "or pick Gemini as the variation model."
                    )
                )
            result = await generate_img2img_with_comfyui(
                source_bytes=source_bytes,
                prompt=prompt or "high quality variation",
                comfyui_url=active_comfyui_url,
                comfyui_dir=comfyui_dir,
                workflow_id=chosen_workflow,
                source_mime=source_mime,
                mask_bytes=mask_bytes,
                mask_mime=mask_mime,
                denoise=denoise,
                mask_grow=mask_grow,
                mask_feather=mask_feather,
                poll_timeout_seconds=await _get_comfyui_poll_timeout_seconds(db),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{model}' does not support image variations"
            )
        
        # Store the variation — _store_image() writes binary to data/images/{id}.{ext}
        variation_id = str(uuid.uuid4())
        IMAGE_STORAGE[variation_id] = {
            "base64": result["base64"],
            "prompt": prompt,
            "revised_prompt": result.get("revised_prompt"),
            "format": format,
            "size": size,
            "model": model,
            "negative_prompt": negative_prompt,
            "variation_of": image_id,
        }

        width, height = map(int, size.split('x'))

        _store_image(variation_id, IMAGE_STORAGE[variation_id])

        from datetime import datetime as _dt
        return ImageListResponse(
            data=[ImageResponse(
                id=variation_id,
                url=f"/v1/img/{variation_id}",
                revised_prompt=result.get("revised_prompt"),
                width=width,
                height=height,
                format=format,
                prompt=prompt,
                model=model,
                created_at=_dt.utcnow().isoformat() + "Z",
                variation_of=image_id,
            )],
            total=1
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image variation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Image variation failed: {str(e)}"
        )




# ─── Image Upload + Editing ────────────────────────────────────────────────────

class ImageEditRequest(BaseModel):
    source_image_id: Optional[str] = None  # ID of previously uploaded/generated image
    source_base64: Optional[str] = None    # Or raw base64 upload
    source_mime: str = "image/png"
    prompt: str                            # Edit instruction
    size: str = "1024x1024"
    model: Optional[str] = None
    workflow_id: Optional[str] = None
    denoise: Optional[float] = None
    mask_base64: Optional[str] = None
    mask_mime: str = "image/png"
    mask_grow: Optional[int] = None
    mask_feather: Optional[float] = None


class ImageUploadRequest(BaseModel):
    base64: str
    filename: Optional[str] = None
    mime_type: str = "image/png"


@router.post("/upload")
async def upload_image(req: ImageUploadRequest):
    """Upload an image for later editing or reference."""
    image_id = str(uuid.uuid4())

    # Try to detect actual image dimensions
    size = "0x0"
    try:
        img_bytes = base64.b64decode(req.base64)
        from io import BytesIO
        from PIL import Image as PILImage
        with PILImage.open(BytesIO(img_bytes)) as img:
            size = f"{img.width}x{img.height}"
    except Exception:
        pass  # Pillow not available or bad data — fall back gracefully

    _store_image(image_id, {
        "base64": req.base64,
        "prompt": f"Uploaded: {req.filename or 'image'}",
        "revised_prompt": None,
        "format": req.mime_type.split("/")[-1] if "/" in req.mime_type else "png",
        "size": size,
        "model": "upload",
        "negative_prompt": None,
    })

    return {
        "id": image_id,
        "url": f"/v1/img/{image_id}",
        "message": "Image uploaded successfully",
    }


async def _gemini_image_edit(source_base64: str, source_mime: str, prompt: str, api_key: str) -> dict:
    """Edit an image using Gemini's multimodal image generation."""
    model_name = "gemini-2.5-flash-image"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": source_mime, "data": source_base64}},
                {"text": f"Generate an image: {prompt}"},
            ]
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
        }
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload, headers={"Content-Type": "application/json"})

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code,
                                detail=f"Gemini image edit failed: {response.text[:200]}")

        data = response.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise HTTPException(status_code=500, detail="Gemini returned no candidates for edit")

    parts = candidates[0].get("content", {}).get("parts", [])
    for part in parts:
        inline_data = part.get("inlineData")
        if inline_data and inline_data.get("mimeType", "").startswith("image/"):
            return {
                "base64": inline_data["data"],
                "revised_prompt": prompt,
                "mime_type": inline_data.get("mimeType", "image/png"),
            }

    # Check for text response (Gemini refused to edit)
    text_parts = [p.get("text", "") for p in parts if "text" in p]
    detail = " ".join(text_parts) if text_parts else "No image in response"
    raise HTTPException(status_code=500, detail=f"Gemini did not return an edited image: {detail[:200]}")


@router.post("/edit", response_model=ImageListResponse)
@router.post("/edit/async")
async def edit_image_async(req: ImageEditRequest, db: AsyncSession = Depends(get_db)):
    """Queue an image edit as a background job. Returns job_id immediately."""
    # Resolve source image up front so we can 404 early
    source_b64 = req.source_base64
    source_mime = req.source_mime or "image/png"
    source_image_id = req.source_image_id

    if source_image_id:
        if source_image_id in IMAGE_STORAGE:
            stored = IMAGE_STORAGE[source_image_id]
            source_b64 = stored.get("base64") or _load_image_base64(
                source_image_id, stored.get("format", "png"))
            fmt = stored.get("format", "png")
            source_mime = f"image/{fmt}" if fmt != "jpg" else "image/jpeg"
        else:
            source_b64 = _load_image_base64(source_image_id)
            if not source_b64:
                raise HTTPException(status_code=404, detail="Source image not found")

    if not source_b64:
        raise HTTPException(status_code=400, detail="Provide either source_image_id or source_base64")

    job_id = str(uuid.uuid4())
    _job_create(job_id, "edit", source_image_id=source_image_id)

    # Capture all request fields for closure
    _req_prompt = req.prompt
    _req_model = req.model
    _req_size = req.size
    _req_workflow_id = req.workflow_id
    _req_denoise = req.denoise
    _req_mask_grow = req.mask_grow
    _req_mask_feather = req.mask_feather
    _req_mask_base64 = req.mask_base64
    _req_mask_mime = req.mask_mime or "image/png"
    _req_source_b64 = source_b64
    _req_source_mime = source_mime

    # Determine original model/workflow from stored metadata
    original_model = None
    original_workflow_id = None
    if source_image_id and source_image_id in IMAGE_STORAGE:
        _st = IMAGE_STORAGE[source_image_id]
        original_model = _st.get("model")
        original_workflow_id = _st.get("workflow_id")

    configured_comfyui_url = await get_setting("comfyui_url", db)
    comfyui_dir = await get_setting("comfyui_dir", db)
    poll_timeout = await _get_comfyui_poll_timeout_seconds(db)

    async def _run():
        try:
            _job_update(job_id, status="running", message="Starting…")
            preferred_model = _req_model or original_model
            chosen_workflow = _req_workflow_id or original_workflow_id or "sdxl-img2img"
            denoise = _resolve_denoise(_req_denoise, 0.45)
            mask_grow = _resolve_mask_grow(_req_mask_grow, 8)
            mask_feather = _resolve_mask_feather(_req_mask_feather, 6.0)

            mask_bytes = None
            if _req_mask_base64:
                try:
                    mask_bytes = base64.b64decode(_req_mask_base64)
                except Exception as exc:
                    _job_update(job_id, status="error", error=f"Invalid mask_base64: {exc}")
                    return

            try:
                source_bytes = base64.b64decode(_req_source_b64)
            except Exception as exc:
                _job_update(job_id, status="error", error=f"Invalid source image: {exc}")
                return

            result = None
            used_model = preferred_model or original_model

            if preferred_model == "comfyui-local":
                progress_cb = _make_job_progress_cb(job_id)
                try:
                    _ensure_comfyui_png_source(_req_source_mime, "edits")
                    active_comfyui_url = await _resolve_comfyui_endpoint(configured_comfyui_url)
                    if not active_comfyui_url:
                        raise Exception(
                            f"ComfyUI not reachable at configured URL(s): {configured_comfyui_url}"
                        )
                    result = await generate_img2img_with_comfyui(
                        source_bytes=source_bytes,
                        prompt=_req_prompt,
                        comfyui_url=active_comfyui_url,
                        workflow_id=chosen_workflow,
                        comfyui_dir=comfyui_dir,
                        source_mime=_req_source_mime,
                        mask_bytes=mask_bytes,
                        mask_mime=_req_mask_mime,
                        denoise=denoise,
                        mask_grow=mask_grow,
                        mask_feather=mask_feather,
                        poll_timeout_seconds=poll_timeout,
                        progress_cb=progress_cb,
                    )
                    used_model = "comfyui-local"
                except Exception as comfy_err:
                    logger.warning(f"ComfyUI failed for async edit, falling back to Gemini: {comfy_err}")
                    used_model = None

            if result is None:
                api_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                           or getattr(settings, "gemini_api_key", None))
                if not api_key:
                    _job_update(job_id, status="error", error="Gemini API key required for image editing")
                    return
                _job_update(job_id, status="running", message="Sending to Gemini…")
                result = await _gemini_image_edit(_req_source_b64, _req_source_mime, _req_prompt, api_key)
                used_model = "gemini-image-edit"

            # Store result
            new_image_id = str(uuid.uuid4())
            fmt = result.get("mime_type", "image/png").split("/")[-1]
            if fmt == "jpeg":
                fmt = "jpg"
            size_str = _req_size or "1024x1024"
            width, height = map(int, size_str.split("x")) if "x" in size_str else (1024, 1024)
            _store_image(new_image_id, {
                "base64": result["base64"],
                "prompt": _req_prompt,
                "revised_prompt": result.get("revised_prompt"),
                "format": fmt,
                "size": size_str,
                "model": used_model,
                "workflow_id": chosen_workflow if used_model == "comfyui-local" else original_workflow_id,
                "source_image_id": source_image_id,
            })
            _job_update(job_id, status="complete", result_image_id=new_image_id,
                        message="Done", step=1, max_steps=1)
        except Exception as exc:
            logger.exception(f"Async edit job {job_id} failed")
            _job_update(job_id, status="error", error=str(exc))

    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "pending"}


async def edit_image(req: ImageEditRequest, db: AsyncSession = Depends(get_db)):  # noqa: C901
    """Edit an image using AI — upload a photo and describe what you want."""

    # Get source image base64
    source_b64 = req.source_base64
    source_mime = req.source_mime

    if req.source_image_id:
        # Load from stored image
        if req.source_image_id in IMAGE_STORAGE:
            stored = IMAGE_STORAGE[req.source_image_id]
            source_b64 = stored.get("base64") or _load_image_base64(
                req.source_image_id, stored.get("format", "png"))
            fmt = stored.get("format", "png")
            source_mime = f"image/{fmt}" if fmt != "jpg" else "image/jpeg"
        else:
            # Try loading from disk
            source_b64 = _load_image_base64(req.source_image_id)
            if not source_b64:
                raise HTTPException(status_code=404, detail="Source image not found")

    if not source_b64:
        raise HTTPException(status_code=400,
                            detail="Provide either source_image_id or source_base64")

    try:
        source_bytes = base64.b64decode(source_b64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid source image payload: {exc}")

    mask_bytes = None
    if req.mask_base64:
        try:
            mask_bytes = base64.b64decode(req.mask_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid mask_base64 payload: {exc}")

    # Determine which model originally created this image
    original_model = None
    original_workflow_id = None
    if req.source_image_id and req.source_image_id in IMAGE_STORAGE:
        stored = IMAGE_STORAGE[req.source_image_id]
        original_model = stored.get("model")
        original_workflow_id = stored.get("workflow_id")

    result = None
    preferred_model = req.model or original_model
    used_model = preferred_model or original_model
    chosen_workflow = req.workflow_id or original_workflow_id or "sdxl-img2img"
    denoise = _resolve_denoise(req.denoise, 0.45)
    mask_grow = _resolve_mask_grow(req.mask_grow, 8)
    mask_feather = _resolve_mask_feather(req.mask_feather, 6.0)

    # Try original model first (same priority as variations endpoint)
    if preferred_model == "comfyui-local":
        configured_comfyui_url = await get_setting("comfyui_url", db)
        comfyui_dir = await get_setting("comfyui_dir", db)
        try:
            _ensure_comfyui_png_source(source_mime, "edits")
            active_comfyui_url = await _resolve_comfyui_endpoint(configured_comfyui_url)
            if not active_comfyui_url:
                raise Exception(
                    f"ComfyUI not reachable at configured URL(s): {configured_comfyui_url}"
                )
            result = await generate_img2img_with_comfyui(
                source_bytes=source_bytes,
                prompt=req.prompt,
                comfyui_url=active_comfyui_url,
                workflow_id=chosen_workflow,
                comfyui_dir=comfyui_dir,
                source_mime=source_mime,
                mask_bytes=mask_bytes,
                mask_mime=req.mask_mime,
                denoise=denoise,
                mask_grow=mask_grow,
                mask_feather=mask_feather,
                poll_timeout_seconds=await _get_comfyui_poll_timeout_seconds(db),
            )
            used_model = "comfyui-local"
        except Exception as comfy_err:
            logger.warning(f"ComfyUI failed for edit, falling back to Gemini: {comfy_err}")
            used_model = None  # will fall through to Gemini below

    # Gemini editing (default, or fallback from ComfyUI)
    if result is None:
        api_key = (os.environ.get('GEMINI_API_KEY')
                   or os.environ.get('GOOGLE_API_KEY')
                   or getattr(settings, 'gemini_api_key', None))
        if not api_key:
            raise HTTPException(status_code=503, detail="Gemini API key required for image editing")
        result = await _gemini_image_edit(source_b64, source_mime, req.prompt, api_key)
        used_model = "gemini-image-edit"

    # Store result
    image_id = str(uuid.uuid4())
    fmt = result.get("mime_type", "image/png").split("/")[-1]
    if fmt == "jpeg": fmt = "jpg"
    width, height = map(int, req.size.split("x")) if "x" in req.size else (1024, 1024)

    _store_image(image_id, {
        "base64": result["base64"],
        "prompt": req.prompt,
        "revised_prompt": result.get("revised_prompt"),
        "format": fmt,
        "size": req.size,
        "model": used_model,
        "workflow_id": chosen_workflow if used_model == "comfyui-local" else original_workflow_id,
        "source_image_id": req.source_image_id,
    })

    return ImageListResponse(
        data=[ImageResponse(
            id=image_id,
            url=f"/v1/images/{image_id}",
            revised_prompt=result.get("revised_prompt"),
            width=width,
            height=height,
            format=fmt,
        )],
        total=1,
    )

@public_router.get("/{image_id}")
async def serve_image_public(image_id: str):
    """Serve image binary without auth — for <img src> tags."""
    fmt = "png"
    if image_id in IMAGE_STORAGE:
        fmt = IMAGE_STORAGE[image_id].get("format", "png")

    # Try loading from disk
    for ext in [fmt, "png", "jpg", "jpeg", "webp"]:
        p = _IMAGE_DIR / f"{image_id}.{ext}"
        if p.exists():
            media_type = f"image/{ext}" if ext != "jpg" else "image/jpeg"
            return Response(content=p.read_bytes(), media_type=media_type)

    raise HTTPException(status_code=404, detail="Image not found")