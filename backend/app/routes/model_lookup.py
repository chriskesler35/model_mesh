"""Model lookup endpoints for fetching model info from providers."""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/model-lookup", tags=["model-lookup"])


class ModelLookupRequest(BaseModel):
    model_id: str
    provider: str


class ModelLookupResponse(BaseModel):
    model_id: str
    display_name: Optional[str] = None
    context_window: Optional[int] = None
    cost_per_1m_input: Optional[float] = None
    cost_per_1m_output: Optional[float] = None
    capabilities: Optional[Dict[str, Any]] = None
    source: str  # Where the info came from


# Known model pricing data (fallback when API lookup fails)
MODEL_PRICING = {
    # OpenAI models
    "gpt-4o": {"input": 2.50, "output": 10.00, "context": 128000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "context": 128000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00, "context": 128000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "gpt-4": {"input": 30.00, "output": 60.00, "context": 8192, "capabilities": {"chat": True, "streaming": True}},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50, "context": 16385, "capabilities": {"chat": True, "streaming": True}},
    
    # Anthropic models
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "claude-sonnet-4": {"input": 3.00, "output": 15.00, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "claude-opus-4": {"input": 15.00, "output": 75.00, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "claude-3-opus": {"input": 15.00, "output": 75.00, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "claude-3-haiku": {"input": 0.25, "output": 1.25, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    
    # Google models
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00, "context": 1000000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "context": 1000000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00, "context": 2000000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30, "context": 1000000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "gemini-1.0-pro": {"input": 0.50, "output": 1.50, "context": 32760, "capabilities": {"chat": True, "streaming": True}},
    "gemini-3.1-pro-preview": {"input": 1.25, "output": 5.00, "context": 2000000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    
    # OpenRouter models (prefixed)
    "openai/gpt-4o": {"input": 2.50, "output": 10.00, "context": 128000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "openai/gpt-4-turbo": {"input": 10.00, "output": 30.00, "context": 128000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "anthropic/claude-opus-4": {"input": 15.00, "output": 75.00, "context": 200000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    "google/gemini-2.5-pro": {"input": 1.25, "output": 5.00, "context": 1000000, "capabilities": {"chat": True, "vision": True, "streaming": True}},
    
    # Meta Llama models
    "llama3.1:8b": {"input": 0, "output": 0, "context": 128000, "capabilities": {"chat": True, "streaming": True}, "display_name": "Llama 3.1 8B"},
    "llama3.1:70b": {"input": 0, "output": 0, "context": 128000, "capabilities": {"chat": True, "streaming": True}, "display_name": "Llama 3.1 70B"},
    "llama3.2:3b": {"input": 0, "output": 0, "context": 128000, "capabilities": {"chat": True, "streaming": True}, "display_name": "Llama 3.2 3B"},
    "llama3.2:1b": {"input": 0, "output": 0, "context": 128000, "capabilities": {"chat": True, "streaming": True}, "display_name": "Llama 3.2 1B"},
    
    # Other common models
    "glm-5:cloud": {"input": 0, "output": 0, "context": 128000, "capabilities": {"chat": True, "streaming": True}, "display_name": "GLM-5 Cloud"},
    "qwen2.5-coder:14b": {"input": 0, "output": 0, "context": 32768, "capabilities": {"chat": True, "streaming": True, "code": True}, "display_name": "Qwen 2.5 Coder 14B"},
    "qwen2.5-coder:32b": {"input": 0, "output": 0, "context": 32768, "capabilities": {"chat": True, "streaming": True, "code": True}, "display_name": "Qwen 2.5 Coder 32B"},
    "mistral-small": {"input": 0.10, "output": 0.30, "context": 128000, "capabilities": {"chat": True, "streaming": True}},
    "mistral-large": {"input": 2.00, "output": 6.00, "context": 128000, "capabilities": {"chat": True, "streaming": True}},
    "deepseek-chat": {"input": 0.14, "output": 0.28, "context": 64000, "capabilities": {"chat": True, "streaming": True}},
    "deepseek-coder": {"input": 0.14, "output": 0.28, "context": 64000, "capabilities": {"chat": True, "streaming": True, "code": True}},
    
    # Image models
    "gemini-imagen": {"input": 0, "output": 0, "context": None, "capabilities": {"image_generation": True}, "display_name": "Gemini Imagen"},
    "dall-e-3": {"input": 0.04, "output": 0, "context": None, "capabilities": {"image_generation": True}, "display_name": "DALL-E 3"},
    "comfyui-local": {"input": 0, "output": 0, "context": None, "capabilities": {"image_generation": True}, "display_name": "ComfyUI Local"},
    "stable-diffusion-xl": {"input": 0, "output": 0, "context": None, "capabilities": {"image_generation": True}, "display_name": "SDXL"},
}


async def lookup_openrouter_model(model_id: str) -> Optional[Dict[str, Any]]:
    """Lookup model info from OpenRouter API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # OpenRouter has a public models endpoint
            response = await client.get("https://openrouter.ai/api/v1/models")
            if response.status_code == 200:
                data = response.json()
                for model in data.get("data", []):
                    if model.get("id") == model_id:
                        pricing = model.get("pricing", {})
                        return {
                            "context_window": model.get("context_length"),
                            "cost_per_1m_input": float(pricing.get("input", 0)) * 1000000 if pricing.get("input") else None,
                            "cost_per_1m_output": float(pricing.get("output", 0)) * 1000000 if pricing.get("output") else None,
                            "display_name": model.get("name", model_id),
                            "capabilities": {
                                "chat": True,
                                "streaming": True,
                                "vision": "vision" in model.get("architecture", {}).get("modality", "")
                            }
                        }
    except Exception as e:
        logger.warning(f"Failed to lookup OpenRouter model: {e}")
    return None


async def lookup_ollama_model(model_id: str, base_url: str = "http://localhost:11434") -> Optional[Dict[str, Any]]:
    """Lookup model info from Ollama API."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/api/show", params={"name": model_id})
            if response.status_code == 200:
                data = response.json()
                model_info = data.get("model_info", data.get("details", {}))
                return {
                    "display_name": data.get("details", {}).get("family", model_id),
                    "context_window": model_info.get("context_length", 4096),
                    "cost_per_1m_input": 0,  # Local models are free
                    "cost_per_1m_output": 0,
                    "capabilities": {"chat": True, "streaming": True}
                }
    except Exception as e:
        logger.debug(f"Failed to lookup Ollama model: {e}")
    return None


@router.post("/lookup", response_model=ModelLookupResponse)
async def lookup_model(request: ModelLookupRequest):
    """Look up model information from provider APIs or known data."""
    model_id = request.model_id.lower().strip()
    provider = request.provider.lower()
    
    # Check our known pricing database first
    for key, pricing in MODEL_PRICING.items():
        if model_id == key.lower() or model_id.endswith(key.lower()) or key.lower() in model_id:
            return ModelLookupResponse(
                model_id=request.model_id,
                display_name=pricing.get("display_name", request.model_id),
                context_window=pricing.get("context"),
                cost_per_1m_input=pricing.get("input"),
                cost_per_1m_output=pricing.get("output"),
                capabilities=pricing.get("capabilities", {"chat": True, "streaming": True}),
                source="database"
            )
    
    # Try provider-specific lookups
    if provider == "openrouter":
        result = await lookup_openrouter_model(model_id)
        if result:
            return ModelLookupResponse(
                model_id=request.model_id,
                **result,
                source="openrouter_api"
            )
    
    elif provider == "ollama":
        result = await lookup_ollama_model(model_id)
        if result:
            return ModelLookupResponse(
                model_id=request.model_id,
                **result,
                source="ollama_api"
            )
    
    # Return empty response indicating user input needed
    return ModelLookupResponse(
        model_id=request.model_id,
        display_name=request.model_id,
        source="user_input_required"
    )


@router.get("/suggestions/{provider}")
async def get_model_suggestions(provider: str):
    """Get suggested models for a provider."""
    provider = provider.lower()
    suggestions = []
    
    for model_id, pricing in MODEL_PRICING.items():
        # Include model if it matches the provider
        if provider == "ollama" and (model_id.startswith("llama") or model_id.startswith("qwen") or model_id.startswith("glm")):
            if not model_id.startswith("openai/") and not model_id.startswith("anthropic/"):
                suggestions.append({
                    "model_id": model_id,
                    "display_name": pricing.get("display_name", model_id),
                    "context_window": pricing.get("context"),
                    "cost_per_1m_input": pricing.get("input"),
                    "cost_per_1m_output": pricing.get("output"),
                    "capabilities": pricing.get("capabilities", {})
                })
        elif provider == "anthropic" and (model_id.startswith("claude") and not "/" in model_id):
            suggestions.append({
                "model_id": model_id,
                "display_name": pricing.get("display_name", model_id),
                "context_window": pricing.get("context"),
                "cost_per_1m_input": pricing.get("input"),
                "cost_per_1m_output": pricing.get("output"),
                "capabilities": pricing.get("capabilities", {})
            })
        elif provider == "google" and model_id.startswith("gemini"):
            suggestions.append({
                "model_id": model_id,
                "display_name": pricing.get("display_name", model_id),
                "context_window": pricing.get("context"),
                "cost_per_1m_input": pricing.get("input"),
                "cost_per_1m_output": pricing.get("output"),
                "capabilities": pricing.get("capabilities", {})
            })
        elif provider == "openrouter" and "/" in model_id:
            suggestions.append({
                "model_id": model_id,
                "display_name": pricing.get("display_name", model_id),
                "context_window": pricing.get("context"),
                "cost_per_1m_input": pricing.get("input"),
                "cost_per_1m_output": pricing.get("output"),
                "capabilities": pricing.get("capabilities", {})
            })
    
    return {"provider": provider, "suggestions": suggestions[:10]}  # Max 10 suggestions