"""
Model sync endpoint.

On startup (and on demand):
  1. Probe Ollama — import every locally-installed model.
  2. Check which provider API keys are set — activate those provider model lists.
  3. Upsert everything into the DB (never delete, only add/update).
"""

import uuid
import httpx
import logging
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.model import Model
from app.models.provider import Provider
from app.config import settings
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/models",
    tags=["model-sync"],
    dependencies=[Depends(verify_api_key)],
)

# ---------------------------------------------------------------------------
# Known paid model lists per provider
# Only added when the corresponding API key is present in .env
# ---------------------------------------------------------------------------

PROVIDER_DEFAULT_MODELS: dict[str, list[dict]] = {
    "anthropic": [
        {"model_id": "claude-opus-4-5",        "display_name": "Claude Opus 4.5",       "input": 15.00, "output": 75.00,  "ctx": 200000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "claude-sonnet-4-5",       "display_name": "Claude Sonnet 4.5",     "input":  3.00, "output": 15.00,  "ctx": 200000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "claude-haiku-4-5",        "display_name": "Claude Haiku 4.5",      "input":  0.80, "output":  4.00,  "ctx": 200000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "claude-3-5-sonnet-20241022","display_name":"Claude 3.5 Sonnet",    "input":  3.00, "output": 15.00,  "ctx": 200000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "claude-3-5-haiku-20241022","display_name": "Claude 3.5 Haiku",     "input":  0.80, "output":  4.00,  "ctx": 200000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "claude-3-opus-20240229",   "display_name": "Claude 3 Opus",        "input": 15.00, "output": 75.00,  "ctx": 200000, "caps": {"chat": True, "vision": True, "streaming": True}},
    ],
    "google": [
        {"model_id": "gemini-2.5-pro",          "display_name": "Gemini 2.5 Pro",        "input":  1.25, "output":  5.00,  "ctx": 1000000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "gemini-2.5-flash",        "display_name": "Gemini 2.5 Flash",      "input":  0.15, "output":  0.60,  "ctx": 1000000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "gemini-2.0-flash",        "display_name": "Gemini 2.0 Flash",      "input":  0.10, "output":  0.40,  "ctx": 1000000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "gemini-1.5-pro",          "display_name": "Gemini 1.5 Pro",        "input":  1.25, "output":  5.00,  "ctx": 2000000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "gemini-1.5-flash",        "display_name": "Gemini 1.5 Flash",      "input": 0.075, "output":  0.30,  "ctx": 1000000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "gemini-imagen-3",         "display_name": "Gemini Imagen 3",       "input":  0,    "output":  0,     "ctx": None,    "caps": {"image_generation": True}},
    ],
    "openai": [
        {"model_id": "gpt-4o",                  "display_name": "GPT-4o",                "input":  2.50, "output": 10.00,  "ctx": 128000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "gpt-4o-mini",             "display_name": "GPT-4o Mini",           "input":  0.15, "output":  0.60,  "ctx": 128000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "gpt-4-turbo",             "display_name": "GPT-4 Turbo",           "input": 10.00, "output": 30.00,  "ctx": 128000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "o1-mini",                 "display_name": "o1 Mini",               "input":  1.10, "output":  4.40,  "ctx": 128000, "caps": {"chat": True, "streaming": True}},
        {"model_id": "o3-mini",                 "display_name": "o3 Mini",               "input":  1.10, "output":  4.40,  "ctx": 200000, "caps": {"chat": True, "streaming": True}},
    ],
    "openrouter": [
        {"model_id": "anthropic/claude-opus-4",      "display_name": "Claude Opus 4 (OR)",    "input": 15.00, "output": 75.00, "ctx": 200000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "anthropic/claude-sonnet-4",    "display_name": "Claude Sonnet 4 (OR)",  "input":  3.00, "output": 15.00, "ctx": 200000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "openai/gpt-4o",                "display_name": "GPT-4o (OR)",           "input":  2.50, "output": 10.00, "ctx": 128000, "caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "google/gemini-2.5-pro",        "display_name": "Gemini 2.5 Pro (OR)",   "input":  1.25, "output":  5.00, "ctx": 1000000,"caps": {"chat": True, "vision": True, "streaming": True}},
        {"model_id": "meta-llama/llama-3.1-405b-instruct","display_name":"Llama 3.1 405B (OR)","input": 0.80, "output":  0.80, "ctx": 131072, "caps": {"chat": True, "streaming": True}},
        {"model_id": "mistralai/mistral-large",      "display_name": "Mistral Large (OR)",    "input":  2.00, "output":  6.00, "ctx": 128000, "caps": {"chat": True, "streaming": True}},
        {"model_id": "deepseek/deepseek-chat",       "display_name": "DeepSeek Chat (OR)",    "input":  0.14, "output":  0.28, "ctx": 64000,  "caps": {"chat": True, "streaming": True}},
        {"model_id": "openrouter/auto",              "display_name": "OpenRouter Auto",       "input":  0,    "output":  0,    "ctx": 200000, "caps": {"chat": True, "streaming": True}},
    ],
}

# Map provider name → which settings key holds its API key
PROVIDER_KEY_MAP = {
    "anthropic":  lambda: settings.anthropic_api_key,
    "google":     lambda: settings.google_api_key or settings.gemini_api_key,
    "openai":     lambda: settings.openai_api_key,
    "openrouter": lambda: settings.openrouter_api_key,
}


# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------

async def fetch_ollama_models(base_url: str) -> list[dict]:
    """Return list of models from Ollama /api/tags. Uses httpx if available, falls back to urllib."""
    url = f"{base_url}/api/tags"

    # Try httpx first (async, preferred)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            if r.status_code == 200:
                return r.json().get("models", [])
    except ImportError:
        pass  # httpx not available, fall through to urllib
    except Exception as e:
        logger.debug(f"Ollama httpx probe failed: {e}")

    # Fallback: urllib (stdlib, always available)
    try:
        import urllib.request, json as _json
        with urllib.request.urlopen(url, timeout=5) as resp:
            return _json.loads(resp.read()).get("models", [])
    except Exception as e:
        logger.debug(f"Ollama urllib probe failed: {e}")

    return []


async def fetch_ollama_model_info(model_name: str, base_url: str) -> dict:
    """Fetch details for a single Ollama model."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{base_url}/api/show", json={"name": model_name})
            if r.status_code == 200:
                return r.json()
    except Exception:
        pass
    return {}


def infer_capabilities(model_name: str) -> dict:
    """Guess capabilities from model name."""
    name = model_name.lower()
    caps: dict = {"chat": True, "streaming": True, "completion": True}
    if any(x in name for x in ["vision", "vl", "llava", "bakllava", "moondream", "minicpm-v"]):
        caps["vision"] = True
    if any(x in name for x in ["coder", "code", "deepseek-coder", "codellama", "starcoder", "qwen.*coder"]):
        caps["code"] = True
    if any(x in name for x in ["embed", "nomic-embed", "mxbai-embed", "snowflake-arctic-embed"]):
        caps = {"embedding": True}  # embedding-only
    return caps


def nice_display_name(model_id: str) -> str:
    """Turn 'llama3.2:3b' into 'Llama 3.2 3B'."""
    base = model_id.split(":")[0]
    tag  = model_id.split(":")[1] if ":" in model_id else ""
    name = base.replace("-", " ").replace("_", " ").title()
    if tag:
        name += f" {tag.upper()}"
    return name


# ---------------------------------------------------------------------------
# Core sync logic (shared by endpoint + startup)
# ---------------------------------------------------------------------------

async def run_model_sync(db: AsyncSession) -> dict:
    """
    Sync Ollama models + enabled paid providers into the DB.
    Returns a summary dict.
    """
    added = []
    skipped = []
    errors = []

    # ── ensure providers exist ────────────────────────────────────────────────
    all_providers_result = await db.execute(select(Provider))
    providers_by_name: dict[str, Provider] = {
        p.name: p for p in all_providers_result.scalars().all()
    }

    async def get_or_create_provider(name: str, display: str, api_base: str, auth_type: str) -> Provider:
        if name in providers_by_name:
            return providers_by_name[name]
        p = Provider(
            id=uuid.uuid4(),
            name=name,
            display_name=display,
            api_base_url=api_base,
            auth_type=auth_type,
            is_active=True,
        )
        db.add(p)
        await db.flush()
        providers_by_name[name] = p
        return p

    # Ensure Ollama provider exists
    ollama_provider = await get_or_create_provider(
        "ollama", "Ollama",
        settings.ollama_base_url or "http://localhost:11434",
        "none",
    )

    # ── existing model index (provider_id, model_id) ─────────────────────────
    existing_result = await db.execute(select(Model))
    existing: dict[tuple, Model] = {
        (str(m.provider_id), m.model_id): m
        for m in existing_result.scalars().all()
    }

    def upsert_model(
        provider: Provider,
        model_id: str,
        display_name: str,
        cost_in: float,
        cost_out: float,
        ctx: Optional[int],
        caps: dict,
    ) -> bool:
        """Upsert a model. Returns True if it was new."""
        key = (str(provider.id), model_id)
        if key in existing:
            return False  # already there
        m = Model(
            id=uuid.uuid4(),
            provider_id=provider.id,
            model_id=model_id,
            display_name=display_name,
            cost_per_1m_input=cost_in,
            cost_per_1m_output=cost_out,
            context_window=ctx,
            capabilities=caps,
            is_active=True,
        )
        db.add(m)
        existing[key] = m
        return True

    # ── 1. Ollama ─────────────────────────────────────────────────────────────
    ollama_url = settings.ollama_base_url or "http://localhost:11434"
    ollama_raw = await fetch_ollama_models(ollama_url)

    if ollama_raw:
        for entry in ollama_raw:
            model_id = entry.get("name", "")
            if not model_id:
                continue
            # Fetch details for context window
            info = await fetch_ollama_model_info(model_id, ollama_url)
            model_info_block = info.get("model_info", info.get("details", {}))
            ctx_window = model_info_block.get("context_length") or model_info_block.get("num_ctx") or 4096

            display = nice_display_name(model_id)
            caps = infer_capabilities(model_id)

            if upsert_model(ollama_provider, model_id, display, 0.0, 0.0, ctx_window, caps):
                added.append(f"ollama/{model_id}")
            else:
                skipped.append(f"ollama/{model_id}")
        logger.info(f"Ollama sync: {len(ollama_raw)} models found")
    else:
        logger.info("Ollama not reachable — skipping local model sync")

    # ── 2. Paid providers (key-gated) ─────────────────────────────────────────
    for provider_name, models_list in PROVIDER_DEFAULT_MODELS.items():
        key_fn = PROVIDER_KEY_MAP.get(provider_name)
        if not key_fn or not key_fn():
            logger.debug(f"Skipping {provider_name} — no API key set")
            continue

        # Map display names / api_base
        meta = {
            "anthropic":  ("Anthropic",  "https://api.anthropic.com",                 "api_key"),
            "google":     ("Google",     "https://generativelanguage.googleapis.com",  "api_key"),
            "openai":     ("OpenAI",     "https://api.openai.com",                    "api_key"),
            "openrouter": ("OpenRouter", "https://openrouter.ai/api",                 "api_key"),
        }
        display_name, api_base, auth_type = meta[provider_name]
        provider = await get_or_create_provider(provider_name, display_name, api_base, auth_type)

        for m in models_list:
            if upsert_model(
                provider, m["model_id"], m["display_name"],
                m["input"], m["output"], m.get("ctx"), m["caps"],
            ):
                added.append(f"{provider_name}/{m['model_id']}")
            else:
                skipped.append(f"{provider_name}/{m['model_id']}")

    await db.commit()

    summary = {
        "added": added,
        "skipped_existing": len(skipped),
        "errors": errors,
        "ollama_available": len(ollama_raw) > 0,
        "ollama_models": len([a for a in added if a.startswith("ollama/")]),
        "paid_models": len([a for a in added if not a.startswith("ollama/")]),
    }
    logger.info(f"Model sync complete: {len(added)} added, {len(skipped)} already existed")
    return summary


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


@router.post("/sync")
async def sync_models(db: AsyncSession = Depends(get_db)):
    """
    Sync all available models into the DB:
    - Ollama: auto-discovers all locally installed models
    - Paid providers: adds defaults for any provider with an API key in .env
    """
    result = await run_model_sync(db)
    return {
        "ok": True,
        "message": f"Sync complete. {len(result['added'])} new models added.",
        **result,
    }


@router.get("/sync/status")
async def sync_status(db: AsyncSession = Depends(get_db)):
    """
    Returns which providers are configured (API key present) and
    whether Ollama is reachable — without making any DB changes.
    """
    ollama_url = settings.ollama_base_url or "http://localhost:11434"
    ollama_models = await fetch_ollama_models(ollama_url)

    providers_status = {}
    for name, key_fn in PROVIDER_KEY_MAP.items():
        providers_status[name] = bool(key_fn())

    # Count models already in DB per provider
    result = await db.execute(
        select(Model, Provider).join(Provider, Model.provider_id == Provider.id)
    )
    counts: dict[str, int] = {}
    for model, provider in result:
        counts[provider.name] = counts.get(provider.name, 0) + 1

    return {
        "ollama": {
            "reachable": len(ollama_models) > 0,
            "model_count": len(ollama_models),
            "in_db": counts.get("ollama", 0),
        },
        "providers": {
            name: {
                "key_set": has_key,
                "in_db": counts.get(name, 0),
            }
            for name, has_key in providers_status.items()
        },
    }
