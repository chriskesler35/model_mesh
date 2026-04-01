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
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Model
from app.middleware.auth import verify_api_key
from app.config import settings
from app.services.app_settings_helper import get_setting
from app.routes.workflows import find_workflow_path, _convert_editor_to_api
from pydantic import BaseModel
from typing import Optional, List
import os

logger = logging.getLogger(__name__)

# ─── ComfyUI auto-launch ──────────────────────────────────────────────────────

# ComfyUI paths are now configurable via Settings > Image Generation
# Priority: DB settings > .env > defaults (empty = disabled)
_comfyui_proc: Optional[subprocess.Popen] = None


async def _get_comfyui_paths():
    """Load ComfyUI paths from DB settings."""
    from app.database import AsyncSessionLocal
    from app.services.app_settings_helper import get_comfyui_config
    try:
        async with AsyncSessionLocal() as db:
            cfg = await get_comfyui_config(db)
            return cfg
    except Exception:
        return {"dir": "", "python": "", "url": "http://localhost:8188", "gpu_devices": "0"}


async def is_comfyui_running(url: str = "http://localhost:8188") -> bool:
    """Quick TCP health-check against ComfyUI."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{url}/system_stats")
            return r.status_code == 200
    except Exception:
        return False


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
    env["CUDA_VISIBLE_DEVICES"] = gpu_devices
    # Performance env vars
    env["NVIDIA_TF32_OVERRIDE"] = "1"
    env["CUDA_MODULE_LOADING"] = "LAZY"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    cmd = [
        str(comfyui_python), "main.py",
        "--listen", "0.0.0.0",
        "--default-device", "0",  # primary GPU, keeps others visible for overflow
        "--highvram",             # maximize VRAM usage, offload only when needed
        "--async-offload", "2",   # async offload across 2 streams when needed
        "--cuda-malloc",          # faster CUDA memory allocation
        "--fast",                 # enable fast-path optimizations
        "--preview-method", "auto",
        "--enable-cors-header", "*",
    ]
    logger.info(f"Launching ComfyUI: CUDA_VISIBLE_DEVICES={gpu_devices}, cmd={' '.join(cmd[2:])}")

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
    """Store image binary + metadata to disk."""
    # Save binary
    img_bytes = base64.b64decode(data["base64"])
    fmt = data.get("format", "png")
    (_IMAGE_DIR / f"{image_id}.{fmt}").write_bytes(img_bytes)
    # Update in-memory + metadata
    IMAGE_STORAGE[image_id] = data
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
            }
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


async def generate_with_comfyui(
    prompt: str,
    comfyui_url: str,
    size: str = "1024x1024",
    negative_prompt: str = None,
    workflow_id: str = None,
    checkpoint: str = None,
    comfyui_dir: str = "",
    lora: str = None,
    lora_strength: float = 1.0,
) -> dict:
    """Generate image using ComfyUI local installation.

    If workflow_id is provided, loads the template from data/workflows/ or the
    ComfyUI installation directories. Otherwise falls back to sdxl-standard
    if it exists, or a minimal hardcoded SDXL workflow.
    """

    width, height = map(int, size.split('x'))

    logger.info(f"ComfyUI gen: workflow={workflow_id}, checkpoint={checkpoint}, lora={lora}, size={size}")

    # Try to load a workflow template
    effective_workflow_id = workflow_id or "sdxl-standard"
    template_path = find_workflow_path(effective_workflow_id, comfyui_dir)
    effective_checkpoint = checkpoint

    if template_path:
        try:
            raw_text = template_path.read_text(encoding="utf-8-sig")  # handle BOM
            template_data = json.loads(raw_text)
            if not effective_checkpoint:
                effective_checkpoint = template_data.get("default_checkpoint", "")
            # Extract the API-format workflow — our templates store it under "workflow"
            workflow_json = template_data.get("workflow", {})
            is_api_format = workflow_json and any(
                isinstance(v, dict) and "class_type" in v for v in workflow_json.values()
            )

            if not is_api_format and "nodes" in template_data:
                # ComfyUI editor-format file — convert to API format
                logger.info(f"Converting editor-format workflow: {template_path.name}")
                workflow_json = _convert_editor_to_api(template_data)
                if workflow_json:
                    is_api_format = True
                else:
                    logger.warning(f"Failed to convert {template_path.name} — no output nodes found")

            if not is_api_format:
                logger.warning(f"Template {template_path.name} has no usable workflow, using fallback")
                workflow = None
            else:
                logger.info(f"ComfyUI using template: {template_path.name}, checkpoint: {effective_checkpoint}")
                workflow = _hydrate_workflow(workflow_json, {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt or "",
                    "width": str(width),
                    "height": str(height),
                    "checkpoint": effective_checkpoint,
                    "lora_name": lora or "",
                    "lora_strength": str(lora_strength),
                })
        except Exception as e:
            logger.warning(f"Failed to load workflow template {effective_workflow_id}: {e}, using fallback")
            workflow = None
    else:
        logger.warning(f"Workflow template not found: {effective_workflow_id}, using fallback")
        workflow = None

    # Fallback: hardcoded minimal SDXL workflow
    if workflow is None:
        seed = random.randint(1, 2**32 - 1)
        ckpt_node = "4"
        model_source = [ckpt_node, 0]  # model output
        clip_source = [ckpt_node, 1]   # clip output

        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": 7.5, "denoise": 1.0,
                    "latent_image": ["5", 0], "model": model_source,
                    "negative": ["7", 0], "positive": ["6", 0],
                    "sampler_name": "euler", "scheduler": "normal",
                    "steps": 20, "seed": seed,
                }
            },
            ckpt_node: {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": effective_checkpoint or "sdxl_base.safetensors"}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"batch_size": 1, "height": height, "width": width}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": clip_source, "text": prompt}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": clip_source, "text": negative_prompt or ""}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": [ckpt_node, 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "modelmesh", "images": ["8", 0]}},
        }

        # Inject LoRA into the fallback workflow
        if lora:
            lora_node_id = "10"
            workflow[lora_node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": lora,
                    "strength_model": lora_strength,
                    "strength_clip": lora_strength,
                    "model": [ckpt_node, 0],
                    "clip": [ckpt_node, 1],
                }
            }
            # Rewire: KSampler + CLIP encoders use LoRA outputs instead of checkpoint
            workflow["3"]["inputs"]["model"] = [lora_node_id, 0]
            workflow["6"]["inputs"]["clip"] = [lora_node_id, 1]
            workflow["7"]["inputs"]["clip"] = [lora_node_id, 1]

    # If LoRA specified and workflow from template doesn't have a LoraLoader, inject one
    if lora and workflow is not None:
        has_lora = any(
            n.get("class_type") == "LoraLoader" for n in workflow.values() if isinstance(n, dict)
        )
        if not has_lora:
            # Find the CheckpointLoaderSimple node and inject LoRA after it
            ckpt_id = None
            for nid, node in workflow.items():
                if isinstance(node, dict) and node.get("class_type") == "CheckpointLoaderSimple":
                    ckpt_id = nid
                    break
            if ckpt_id:
                lora_id = str(max(int(k) for k in workflow.keys() if k.isdigit()) + 1)
                workflow[lora_id] = {
                    "class_type": "LoraLoader",
                    "inputs": {
                        "lora_name": lora,
                        "strength_model": lora_strength,
                        "strength_clip": lora_strength,
                        "model": [ckpt_id, 0],
                        "clip": [ckpt_id, 1],
                    }
                }
                # Rewire nodes that reference the checkpoint's model/clip outputs
                for nid, node in workflow.items():
                    if nid == lora_id or not isinstance(node, dict):
                        continue
                    inputs = node.get("inputs", {})
                    for key, val in inputs.items():
                        if isinstance(val, list) and len(val) == 2 and val[0] == ckpt_id:
                            if val[1] == 0:  # model output
                                inputs[key] = [lora_id, 0]
                            elif val[1] == 1:  # clip output
                                inputs[key] = [lora_id, 1]

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
            
            # Poll for completion — 10 minutes max (model loading + generation on RTX 3060)
            max_poll = 600
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
                            raise HTTPException(status_code=500, detail=f"ComfyUI execution error: {err_detail[:300]}")

                        outputs = entry.get("outputs", {})
                        for node_id, node_output in outputs.items():
                            if "images" in node_output:
                                for img in node_output["images"]:
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
                                        return {
                                            "base64": base64.b64encode(image_bytes).decode('utf-8'),
                                            "revised_prompt": prompt
                                        }
            
            raise HTTPException(
                status_code=504,
                detail=f"ComfyUI generation timed out after {max_poll // 60} minutes"
            )
            
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
                comfyui_url = await get_setting("comfyui_url", db)
                comfyui_dir = await get_setting("comfyui_dir", db)

                # Try ComfyUI; fall back to Gemini on any failure (unreachable, timeout, error)
                comfyui_failed = False
                comfyui_error = ""
                try:
                    comfyui_available = await ensure_comfyui(comfyui_url)
                    if not comfyui_available:
                        raise Exception("ComfyUI not reachable after auto-launch attempt")
                    result = await generate_with_comfyui(
                        request.prompt,
                        comfyui_url,
                        request.size,
                        request.negative_prompt,
                        request.workflow_id,
                        request.checkpoint,
                        comfyui_dir,
                        request.lora,
                        request.lora_strength,
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


@router.get("/{image_id}")
async def get_image(image_id: str):
    """Retrieve a generated image by ID."""
    
    if image_id not in IMAGE_STORAGE:
        raise HTTPException(
            status_code=404,
            detail="Image not found"
        )
    
    image_data = IMAGE_STORAGE[image_id]
    image_bytes = base64.b64decode(image_data["base64"])
    
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
    image_bytes = base64.b64decode(image_data["base64"])
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
    """Delete a generated image."""
    
    if image_id not in IMAGE_STORAGE:
        raise HTTPException(
            status_code=404,
            detail="Image not found"
        )
    
    del IMAGE_STORAGE[image_id]
    
    return {"status": "deleted"}


@router.get("/")
async def list_images(
    limit: int = 50,
    offset: int = 0
):
    """List all generated images."""
    
    images = []
    for image_id, data in list(IMAGE_STORAGE.items())[offset:offset + limit]:
        try:
            width, height = map(int, data["size"].split('x'))
        except (ValueError, AttributeError):
            width, height = 0, 0
        images.append(ImageResponse(
            id=image_id,
            url=f"/v1/images/{image_id}",
            revised_prompt=data.get("revised_prompt"),
            width=width,
            height=height,
            format=data["format"]
        ))
    
    return ImageListResponse(data=images, total=len(IMAGE_STORAGE))


class ImageVariationRequest(BaseModel):
    size: Optional[str] = None  # If None, use original size
    format: Optional[str] = None  # If None, use original format


@router.post("/{image_id}/variations", response_model=ImageListResponse)
async def generate_variation(
    image_id: str,
    request: Optional[ImageVariationRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """Generate a variation of an existing image."""
    
    if image_id not in IMAGE_STORAGE:
        raise HTTPException(
            status_code=404,
            detail="Original image not found"
        )
    
    original = IMAGE_STORAGE[image_id]
    prompt = original["prompt"]
    negative_prompt = original.get("negative_prompt")
    model = original["model"]
    size = request.size if request and request.size else original["size"]
    format = request.format if request and request.format else original["format"]
    
    try:
        if model == "gemini-imagen":
            api_key = os.environ.get('GEMINI_API_KEY') or getattr(settings, 'gemini_api_key', None)
            if not api_key:
                raise HTTPException(
                    status_code=500,
                    detail="GEMINI_API_KEY not configured"
                )
            result = await generate_with_gemini_imagen(prompt, api_key, size)
        elif model == "comfyui-local":
            comfyui_url = await get_setting("comfyui_url", db)
            comfyui_dir = await get_setting("comfyui_dir", db)
            try:
                comfyui_available = await ensure_comfyui(comfyui_url)
                if not comfyui_available:
                    raise Exception("ComfyUI not reachable")
                result = await generate_with_comfyui(prompt, comfyui_url, size, negative_prompt, comfyui_dir=comfyui_dir)
            except Exception as comfy_err:
                # ComfyUI failed (unreachable, timed out, errored) — fall back to Gemini
                logger.warning(f"ComfyUI failed for variation, falling back to Gemini: {comfy_err}")
                api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or getattr(settings, 'gemini_api_key', None)
                if not api_key:
                    raise HTTPException(status_code=503, detail=f"ComfyUI failed ({comfy_err}) and no Gemini API key configured")
                result = await generate_with_gemini_imagen(prompt, api_key, size)
                model = "gemini-imagen"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{model}' does not support image generation"
            )
        
        # Store the variation
        variation_id = str(uuid.uuid4())
        IMAGE_STORAGE[variation_id] = {
            "base64": result["base64"],
            "prompt": prompt,
            "revised_prompt": result.get("revised_prompt"),
            "format": format,
            "size": size,
            "model": model,
            "negative_prompt": negative_prompt,
            "variation_of": image_id
        }
        
        width, height = map(int, size.split('x'))
        
        _store_image(variation_id, IMAGE_STORAGE[variation_id])

        return ImageListResponse(
            data=[ImageResponse(
                id=variation_id,
                url=f"/v1/img/{variation_id}",
                revised_prompt=result.get("revised_prompt"),
                width=width,
                height=height,
                format=format
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
async def edit_image(req: ImageEditRequest, db: AsyncSession = Depends(get_db)):
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

    # Determine which model originally created this image
    original_model = None
    original_negative_prompt = None
    if req.source_image_id and req.source_image_id in IMAGE_STORAGE:
        stored = IMAGE_STORAGE[req.source_image_id]
        original_model = stored.get("model")
        original_negative_prompt = stored.get("negative_prompt")

    result = None
    used_model = original_model

    # Try original model first (same priority as variations endpoint)
    if original_model == "comfyui-local":
        comfyui_url = await get_setting("comfyui_url", db)
        comfyui_dir = await get_setting("comfyui_dir", db)
        try:
            comfyui_available = await ensure_comfyui(comfyui_url)
            if not comfyui_available:
                raise Exception("ComfyUI not reachable")
            result = await generate_with_comfyui(req.prompt, comfyui_url, req.size, original_negative_prompt, comfyui_dir=comfyui_dir)
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
        "negative_prompt": original_negative_prompt,
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