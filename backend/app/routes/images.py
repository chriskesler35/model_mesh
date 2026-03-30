"""Image generation endpoints using Gemini Imagen and ComfyUI."""

import uuid
import base64
import httpx
import logging
import asyncio
import subprocess
import sys
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Model
from app.middleware.auth import verify_api_key
from app.config import settings
from pydantic import BaseModel
from typing import Optional, List
import os

logger = logging.getLogger(__name__)

# ─── ComfyUI auto-launch ──────────────────────────────────────────────────────

COMFYUI_DIR = Path(r"E:\AI_Models\ComfyUI")
COMFYUI_PYTHON = Path(r"C:\Python313\python.exe")
_comfyui_proc: Optional[subprocess.Popen] = None


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

    if not COMFYUI_DIR.exists():
        logger.warning(f"ComfyUI directory not found: {COMFYUI_DIR}")
        return False
    if not COMFYUI_PYTHON.exists():
        logger.warning(f"Python not found at: {COMFYUI_PYTHON}")
        return False

    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = "1,0"

    try:
        _comfyui_proc = subprocess.Popen(
            [str(COMFYUI_PYTHON), "main.py", "--listen", "0.0.0.0"],
            cwd=str(COMFYUI_DIR),
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
    if await is_comfyui_running(url):
        return True
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


async def generate_with_comfyui(prompt: str, comfyui_url: str, size: str = "1024x1024", negative_prompt: str = None) -> dict:
    """Generate image using ComfyUI local installation."""
    
    width, height = map(int, size.split('x'))
    
    # Basic SDXL workflow for ComfyUI
    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": 7.5,
                "denoise": 1.0,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": "euler",
                "scheduler": "normal",
                "steps": 20,
                "seed": 0
            }
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "sdxl_base.safetensors"  # Default, can be configured
            }
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "batch_size": 1,
                "height": height,
                "width": width
            }
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": prompt
            }
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["4", 1],
                "text": negative_prompt or ""
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "modelmesh",
                "images": ["8", 0]
            }
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            # Queue the prompt
            queue_response = await client.post(
                f"{comfyui_url}/prompt",
                json={"prompt": workflow},
                headers={"Content-Type": "application/json"}
            )
            
            if queue_response.status_code != 200:
                error_msg = queue_response.text
                if "ComfyUI" not in comfyui_url or "connection refused" in error_msg.lower():
                    raise HTTPException(
                        status_code=503,
                        detail="ComfyUI not running. Start ComfyUI at http://localhost:8188"
                    )
                raise HTTPException(
                    status_code=500,
                    detail=f"ComfyUI error: {error_msg}"
                )
            
            result = queue_response.json()
            prompt_id = result.get("prompt_id")
            
            if not prompt_id:
                raise HTTPException(
                    status_code=500,
                    detail="ComfyUI did not return a prompt ID"
                )
            
            # Poll for completion
            for attempt in range(120):  # Wait up to 2 minutes
                await asyncio.sleep(1)
                
                history_response = await client.get(
                    f"{comfyui_url}/history/{prompt_id}"
                )
                
                if history_response.status_code == 200:
                    history = history_response.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})
                        
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
                                        return {
                                            "base64": base64.b64encode(image_bytes).decode('utf-8'),
                                            "revised_prompt": prompt
                                        }
            
            raise HTTPException(
                status_code=504,
                detail="ComfyUI generation timed out after 2 minutes"
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
                comfyui_url = os.environ.get('COMFYUI_URL') or getattr(settings, 'comfyui_url', 'http://localhost:8188')

                # Try to ensure ComfyUI is running; fall back to Gemini Imagen if unavailable
                comfyui_available = await ensure_comfyui(comfyui_url)
                if not comfyui_available:
                    logger.warning("ComfyUI unavailable after auto-launch attempt — falling back to Gemini Imagen")
                    # Look up gemini-imagen model for fallback
                    gemini_model_result = await db.execute(
                        select(Model).where(Model.model_id == "gemini-imagen")
                    )
                    gemini_model = gemini_model_result.scalar_one_or_none()
                    if gemini_model:
                        api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or getattr(settings, 'gemini_api_key', None) or getattr(settings, 'google_api_key', None)
                        if not api_key:
                            raise HTTPException(
                                status_code=503,
                                detail="ComfyUI is not running and could not be started. Gemini Imagen fallback requires a Google API key."
                            )
                        result = await generate_with_gemini_imagen(request.prompt, api_key, request.size)
                        request.model = "gemini-imagen"  # update for storage
                    else:
                        raise HTTPException(
                            status_code=503,
                            detail="ComfyUI is not running and could not be started. Add a Gemini API key to enable the fallback image generator."
                        )
                else:
                    result = await generate_with_comfyui(
                        request.prompt,
                        comfyui_url,
                        request.size,
                        request.negative_prompt
                    )
                
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
                "negative_prompt": request.negative_prompt
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
            comfyui_url = os.environ.get('COMFYUI_URL') or getattr(settings, 'comfyui_url', 'http://localhost:8188')
            comfyui_available = await ensure_comfyui(comfyui_url)
            if not comfyui_available:
                logger.warning("ComfyUI unavailable — falling back to Gemini Imagen for variation")
                api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or getattr(settings, 'gemini_api_key', None)
                if not api_key:
                    raise HTTPException(status_code=503, detail="ComfyUI unavailable and no Gemini API key configured")
                result = await generate_with_gemini_imagen(prompt, api_key, size)
                model = "gemini-imagen"
            else:
                result = await generate_with_comfyui(prompt, comfyui_url, size, negative_prompt)
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
        
        return ImageListResponse(
            data=[ImageResponse(
                id=variation_id,
                url=f"/v1/images/{variation_id}",
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
async def edit_image(req: ImageEditRequest):
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

    # Get API key
    api_key = (os.environ.get('GEMINI_API_KEY')
               or os.environ.get('GOOGLE_API_KEY')
               or getattr(settings, 'gemini_api_key', None))
    if not api_key:
        raise HTTPException(status_code=503, detail="Gemini API key required for image editing")

    # Call Gemini
    result = await _gemini_image_edit(source_b64, source_mime, req.prompt, api_key)

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
        "model": "gemini-image-edit",
        "negative_prompt": None,
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