"""Runtime capability snapshot endpoints.

Expose a single source of truth for what is currently usable in this runtime,
including local services (ComfyUI/Ollama) and cloud providers with credentials.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import verify_api_key
from app.routes.model_sync import fetch_ollama_models
from app.routes.workflows import _get_running_comfyui_url
from app.services.provider_credentials import has_provider_api_key


router = APIRouter(prefix="/v1/runtime", tags=["runtime"], dependencies=[Depends(verify_api_key)])


@router.get("/capabilities")
async def runtime_capabilities(db: AsyncSession = Depends(get_db)):
    """Return live runtime capabilities for graceful feature gating in the UI."""
    comfyui_url = await _get_running_comfyui_url(db, timeout=2.5)
    comfyui_available = bool(comfyui_url)

    ollama_base_url = os.environ.get("OLLAMA_BASE_URL") or settings.ollama_base_url or "http://localhost:11434"
    ollama_models = await fetch_ollama_models(ollama_base_url)
    ollama_available = len(ollama_models) > 0

    cloud_providers = {
        "gemini": has_provider_api_key("gemini"),
        "anthropic": has_provider_api_key("anthropic"),
        "openrouter": has_provider_api_key("openrouter"),
        "openai": has_provider_api_key("openai"),
        "openai-codex": has_provider_api_key("openai-codex"),
        "github-copilot": has_provider_api_key("github-copilot"),
    }
    cloud_any_available = any(cloud_providers.values())

    # Prefer local for power users when it's actually available; otherwise cloud.
    if comfyui_available:
        recommended_image_provider = "comfyui-local"
    elif cloud_providers.get("gemini"):
        recommended_image_provider = "gemini-imagen"
    else:
        recommended_image_provider = "gemini-imagen"

    return {
        "local": {
            "comfyui_available": comfyui_available,
            "comfyui_url": comfyui_url,
            "ollama_available": ollama_available,
            "ollama_base_url": ollama_base_url,
            "ollama_model_count": len(ollama_models),
        },
        "cloud": {
            "providers": cloud_providers,
            "any_available": cloud_any_available,
        },
        "image_providers": {
            "comfyui-local": comfyui_available,
            "gemini-imagen": cloud_providers.get("gemini", False),
        },
        "recommended": {
            "image_provider": recommended_image_provider,
        },
    }
