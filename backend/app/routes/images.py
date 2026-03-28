"""Image generation endpoints using Gemini Imagen and ComfyUI."""

import uuid
import base64
import httpx
import logging
import asyncio
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

router = APIRouter(prefix="/v1/images", tags=["images"], dependencies=[Depends(verify_api_key)])


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
IMAGE_STORAGE = {}


async def generate_with_gemini_imagen(prompt: str, api_key: str, size: str = "1024x1024") -> dict:
    """Generate image using Gemini Imagen API via OpenRouter or direct API."""
    
    # Parse dimensions
    width, height = map(int, size.split('x'))
    
    # For now, use a placeholder that returns a generated image URL
    # In production, this would call the actual Gemini Imagen API
    # Gemini's image generation is done through Vertex AI or Imagen API
    
    try:
        # Using Google's Generative AI with image generation
        # Note: This requires the google-generativeai package
        import google.generativeai as genai
        
        genai.configure(api_key=api_key)
        
        # Try to use image generation model
        # Note: Actual API may vary - this is a placeholder
        model = genai.GenerativeModel('imagen-3.0-generate-002')
        
        # Generate image
        response = model.generate_content(
            prompt,
            generation_config={
                "response_modalities": ["image", "text"],
            }
        )
        
        # Extract image from response
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        image_bytes = part.inline_data.data
                        return {
                            "base64": base64.b64encode(image_bytes).decode('utf-8'),
                            "revised_prompt": prompt
                        }
        
        # Fallback: Generate a placeholder
        raise HTTPException(
            status_code=501,
            detail="Gemini image generation requires Vertex AI setup. Use ComfyUI for local generation."
        )
        
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="google-generativeai package not installed"
        )
    except Exception as e:
        logger.error(f"Gemini image generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Image generation failed: {str(e)}"
        )


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
        width, height = map(int, data["size"].split('x'))
        images.append(ImageResponse(
            id=image_id,
            url=f"/v1/images/{image_id}",
            revised_prompt=data.get("revised_prompt"),
            width=width,
            height=height,
            format=data["format"]
        ))
    
    return ImageListResponse(data=images, total=len(IMAGE_STORAGE))