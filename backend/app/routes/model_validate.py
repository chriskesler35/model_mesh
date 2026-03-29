"""Model validation endpoint — confirms a model ID is real and returns authoritative metadata."""

import os
import logging
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
import litellm

from app.middleware.auth import verify_api_key
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/models/validate", tags=["models"], dependencies=[Depends(verify_api_key)])

# Map provider name → litellm model prefix
PROVIDER_PREFIX = {
    "anthropic":  "",          # claude-3-haiku-20240307
    "google":     "gemini/",   # gemini/gemini-2.0-flash
    "openrouter": "openrouter/",
    "ollama":     "ollama/",
    "openai":     "",          # gpt-4o
}

# Capability fields we expose
CAPABILITY_FLAGS = {
    "chat":             "mode",                   # 'chat' mode
    "vision":           "supports_vision",
    "function_calling": "supports_function_calling",
    "streaming":        None,                     # always true for chat models
    "code":             None,                     # infer from model name
}


def _build_litellm_model(provider: str, model_id: str) -> str:
    prefix = PROVIDER_PREFIX.get(provider.lower(), "")
    if prefix and not model_id.startswith(prefix):
        return f"{prefix}{model_id}"
    return model_id


def _get_api_key(provider: str) -> Optional[str]:
    p = provider.lower()
    if p == "google":
        return (os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
                or settings.gemini_api_key
                or settings.google_api_key)
    key_map = {
        "anthropic":  os.environ.get("ANTHROPIC_API_KEY") or settings.anthropic_api_key,
        "openrouter": os.environ.get("OPENROUTER_API_KEY") or settings.openrouter_api_key,
        "openai":     os.environ.get("OPENAI_API_KEY") or settings.openai_api_key,
        "ollama":     None,
    }
    return key_map.get(p)


def _extract_capabilities(info: dict, model_id: str) -> dict:
    caps = {
        "chat": info.get("mode") == "chat",
        "streaming": True,
        "vision": bool(info.get("supports_vision")),
        "function_calling": bool(info.get("supports_function_calling")),
        "code": any(kw in model_id.lower() for kw in ("coder", "codex", "code", "copilot", "starcoder", "deepseek-coder")),
    }
    return {k: v for k, v in caps.items() if v}


class ValidateRequest(BaseModel):
    model_id: str
    provider: str


class ValidateResponse(BaseModel):
    valid: bool
    model_id: str                   # canonical model ID (may differ from input)
    display_name: Optional[str]
    provider: str
    litellm_model: str
    context_window: Optional[int]
    max_output_tokens: Optional[int]
    cost_per_1m_input: Optional[float]
    cost_per_1m_output: Optional[float]
    capabilities: dict
    source: str                     # "litellm_db" | "api_probe" | "unknown"
    warning: Optional[str]          # set if model found in DB but not probe-verified


@router.post("", response_model=ValidateResponse)
async def validate_model(req: ValidateRequest):
    """
    Validate a model ID against the provider and return authoritative metadata.
    - First checks litellm's built-in model database (fast, no API call).
    - If found, returns pricing/context from DB.
    - Then probes the real API with a 1-token completion to confirm the model actually exists.
    """
    provider = req.provider.lower().strip()
    model_id = req.model_id.strip()
    litellm_model = _build_litellm_model(provider, model_id)

    db_info = None
    try:
        db_info = litellm.get_model_info(litellm_model)
    except Exception:
        pass

    # --- Fallback: try without prefix for ollama ---
    if db_info is None and provider == "ollama":
        db_info = {}  # Ollama models aren't in litellm DB; treat as valid

    # Build metadata from DB if available
    context_window = None
    cost_input = None
    cost_output = None
    capabilities = {"chat": True, "streaming": True}
    display_name = None
    source = "unknown"
    warning = None

    if db_info:
        source = "litellm_db"
        context_window = db_info.get("max_input_tokens") or db_info.get("max_tokens")
        max_out = db_info.get("max_output_tokens") or db_info.get("max_tokens")
        raw_in = db_info.get("input_cost_per_token")
        raw_out = db_info.get("output_cost_per_token")
        cost_input  = round(raw_in  * 1_000_000, 4) if raw_in  else 0.0
        cost_output = round(raw_out * 1_000_000, 4) if raw_out else 0.0
        capabilities = _extract_capabilities(db_info, model_id)
        # Build a human display name
        display_name = _humanize(model_id)

    # --- Live API probe (skip for ollama, image-only models) ---
    is_image_only = "imagen" in model_id.lower() or "dall-e" in model_id.lower() or "comfyui" in model_id.lower()
    probe_valid = None

    if provider != "ollama" and not is_image_only:
        api_key = _get_api_key(provider)
        if api_key:
            try:
                kwargs = {
                    "model": litellm_model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 1,
                    "stream": False,
                }
                if provider == "ollama":
                    kwargs["api_base"] = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
                elif provider == "openrouter":
                    kwargs["api_key"] = api_key
                else:
                    kwargs["api_key"] = api_key

                await litellm.acompletion(**kwargs)
                probe_valid = True
                source = "api_probe"
            except litellm.exceptions.NotFoundError:
                probe_valid = False
            except litellm.exceptions.AuthenticationError:
                probe_valid = None  # key issue, not model issue
                warning = "Could not verify — authentication error with provider API"
            except Exception as e:
                probe_valid = None
                warning = f"Could not verify live — {type(e).__name__}"
        else:
            warning = f"No API key configured for {provider} — cannot live-verify"

    # Determine final validity
    if provider == "ollama" or is_image_only:
        valid = True  # can't easily probe, trust the user
    elif probe_valid is True:
        valid = True
    elif probe_valid is False:
        valid = False
    elif db_info is not None:
        valid = True  # in DB = probably valid; warning already set
        if not warning:
            warning = "Found in model database but not live-verified"
    else:
        valid = False

    return ValidateResponse(
        valid=valid,
        model_id=model_id,
        display_name=display_name or _humanize(model_id),
        provider=provider,
        litellm_model=litellm_model,
        context_window=context_window,
        max_output_tokens=db_info.get("max_output_tokens") if db_info else None,
        cost_per_1m_input=cost_input,
        cost_per_1m_output=cost_output,
        capabilities=capabilities,
        source=source,
        warning=warning,
    )


def _humanize(model_id: str) -> str:
    """Convert a model_id like 'gemini/gemini-2.0-flash' into 'Gemini 2.0 Flash'."""
    # Strip provider prefix
    parts = model_id.split("/")
    name = parts[-1]
    # Replace separators, title-case
    name = name.replace("-", " ").replace("_", " ").replace(".", " ")
    return " ".join(w.capitalize() if not w[0].isdigit() else w for w in name.split())
