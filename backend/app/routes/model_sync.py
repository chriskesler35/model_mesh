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
import re
from typing import Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, update
from app.database import get_db
from app.models.model import Model
from app.models.provider import Provider
from app.models.persona import Persona
from app.models.conversation import Message
from app.models.request_log import RequestLog
from app.models.agent import Agent
from app.config import settings
from app.middleware.auth import verify_api_key
from app.services.codex_oauth import get_codex_proxy_api_key, get_codex_proxy_base_url, should_use_codex_oauth_proxy
from app.services.provider_credentials import get_provider_api_key, has_provider_api_key
from app.services.command_executor import get_first_github_token
from app.services.github_copilot import COPILOT_API_BASE, get_copilot_headers

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
    "openai-codex": [
        {"model_id": "gpt-5",               "display_name": "GPT-5 (Codex OAuth)",         "input":  1.25, "output": 10.00, "ctx": 400000, "caps": {"chat": True, "streaming": True, "code": True}},
        {"model_id": "gpt-5-mini",          "display_name": "GPT-5 Mini (Codex OAuth)",    "input":  0.25, "output":  2.00, "ctx": 400000, "caps": {"chat": True, "streaming": True, "code": True}},
        {"model_id": "gpt-4.1",             "display_name": "GPT-4.1 (Codex OAuth)",       "input":  2.00, "output":  8.00, "ctx": 128000, "caps": {"chat": True, "vision": True, "streaming": True, "code": True}},
        {"model_id": "o4-mini",             "display_name": "o4 Mini (Codex OAuth)",       "input":  1.10, "output":  4.40, "ctx": 200000, "caps": {"chat": True, "streaming": True, "code": True}},
        {"model_id": "codex-mini-latest",   "display_name": "Codex Mini Latest",            "input":  1.50, "output":  6.00, "ctx": 200000, "caps": {"chat": True, "streaming": True, "code": True}},
    ],
    "github-copilot": [
        {"model_id": "gpt-4o",                 "display_name": "GPT-4o (GitHub Copilot)",        "input": 0.0, "output": 0.0, "ctx": 128000, "caps": {"chat": True, "vision": True, "streaming": True, "code": True}},
        {"model_id": "gpt-4.1",                "display_name": "GPT-4.1 (GitHub Copilot)",       "input": 0.0, "output": 0.0, "ctx": 128000, "caps": {"chat": True, "streaming": True, "code": True}},
        {"model_id": "claude-3.5-sonnet",      "display_name": "Claude 3.5 Sonnet (Copilot)",    "input": 0.0, "output": 0.0, "ctx": 200000, "caps": {"chat": True, "vision": True, "streaming": True, "code": True}},
        {"model_id": "gemini-2.0-flash-001",   "display_name": "Gemini 2.0 Flash (Copilot)",     "input": 0.0, "output": 0.0, "ctx": 1000000, "caps": {"chat": True, "vision": True, "streaming": True, "code": True}},
    ],
}

PROVIDER_SYNC_META: dict[str, tuple[str, str, str]] = {
    "anthropic": ("Anthropic", "https://api.anthropic.com", "api_key"),
    "google": ("Google", "https://generativelanguage.googleapis.com", "api_key"),
    "openai": ("OpenAI", "https://api.openai.com", "api_key"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api", "api_key"),
    "openai-codex": ("OpenAI Codex", get_codex_proxy_base_url(), "oauth"),
    "github-copilot": ("GitHub Copilot", "https://api.githubcopilot.com", "oauth"),
}

LITELLM_MODEL_PREFIXES: dict[str, str] = {
    "google": "gemini/",
    "openrouter": "openrouter/",
    "openai-codex": "openai/",
    "github-copilot": "openai/",
}

NON_VIABLE_CATALOG_TOKENS = (
    "deprecated",
    "retired",
    "sunset",
    "sunsetting",
    "end of life",
    "end-of-life",
    "eol",
    "obsolete",
    "unsupported",
    "disabled",
    "unavailable",
)

_DATE_SUFFIX_PATTERNS = (
    re.compile(r"[-_](20\d{2})[-_](\d{2})[-_](\d{2})$"),
    re.compile(r"[-_](20\d{2})(\d{2})(\d{2})$"),
)


def _build_litellm_model(provider_name: str, model_id: str) -> str:
    prefix = LITELLM_MODEL_PREFIXES.get((provider_name or "").lower().strip(), "")
    if prefix and not model_id.startswith(prefix):
        return f"{prefix}{model_id}"
    return model_id


def _humanize_model_id(model_id: str) -> str:
    tail = (model_id or "").split("/")[-1]
    tail = tail.replace("-", " ").replace("_", " ").replace(".", " ")
    return " ".join(part.upper() if part.isupper() else part.capitalize() for part in tail.split()) or model_id


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, "", False):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value in (None, "", False):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stringify_catalog_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, dict):
        ordered_keys = (
            "status",
            "state",
            "phase",
            "reason",
            "message",
            "description",
            "note",
            "value",
        )
        parts = [str(value.get(key)).strip() for key in ordered_keys if value.get(key) not in (None, "")]
        return " | ".join(part for part in parts if part)
    if isinstance(value, list):
        return " | ".join(filter(None, (_stringify_catalog_value(item).strip() for item in value)))
    return str(value)


def _catalog_text_is_non_viable(text: str) -> bool:
    normalized = (text or "").strip().lower()
    return bool(normalized and any(token in normalized for token in NON_VIABLE_CATALOG_TOKENS))


def _catalog_reason_from_raw_item(raw_item: dict[str, Any] | None, provider_name: str, model_id: str) -> Optional[str]:
    if not isinstance(raw_item, dict):
        return None

    if raw_item.get("deprecated") is True or raw_item.get("is_deprecated") is True or raw_item.get("isDeprecated") is True:
        return f"{provider_name} marks {model_id} as deprecated."

    for availability_key in ("active", "is_active", "isActive", "available", "is_available", "enabled"):
        if availability_key in raw_item and raw_item.get(availability_key) is False:
            return f"{provider_name} marks {model_id} as unavailable."

    status_fields = (
        "status",
        "state",
        "lifecycle",
        "lifecycle_state",
        "lifecycleState",
        "availability",
        "deprecation",
        "deprecation_status",
        "deprecationStatus",
    )
    for field in status_fields:
        field_text = _stringify_catalog_value(raw_item.get(field)).strip()
        if _catalog_text_is_non_viable(field_text):
            return f"{provider_name} catalog status for {model_id}: {field_text}"

    descriptive_fields = (
        "description",
        "name",
        "display_name",
        "displayName",
    )
    for field in descriptive_fields:
        field_text = _stringify_catalog_value(raw_item.get(field)).strip()
        if _catalog_text_is_non_viable(field_text):
            return f"{provider_name} catalog notes for {model_id}: {field_text}"

    return None


def _mark_catalog_entry_viability(entry: dict[str, Any], raw_item: dict[str, Any] | None, provider_name: str) -> dict[str, Any]:
    reason = _catalog_reason_from_raw_item(raw_item, provider_name, entry.get("model_id", "this model"))
    if reason:
        entry["deprecated"] = True
        entry["deprecation_reason"] = reason
    else:
        entry["deprecated"] = False
        entry["deprecation_reason"] = None
    return entry


def get_catalog_model_viability(model_entry: dict[str, Any]) -> tuple[bool, Optional[str], Optional[str]]:
    if model_entry.get("deprecated"):
        return False, model_entry.get("deprecation_reason") or "Provider catalog marks this model as no longer viable.", "model_deprecated"
    return True, None, None


def _extract_snapshot_date(model_id: str | None):
    if not model_id:
        return None
    tail = str(model_id).split("/")[-1]
    for pattern in _DATE_SUFFIX_PATTERNS:
        match = pattern.search(tail)
        if not match:
            continue
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).date()
        except ValueError:
            continue
    return None


def _model_family_key(model_id: str | None) -> str:
    if not model_id:
        return ""
    parts = str(model_id).split("/")
    tail = parts[-1].lower().strip()
    tail = re.sub(r"[:\-_]?latest$", "", tail)
    for pattern in _DATE_SUFFIX_PATTERNS:
        tail = pattern.sub("", tail)
    tail = tail.rstrip("-_")
    if len(parts) > 1:
        return "/".join(parts[:-1]).lower() + "/" + tail
    return tail


def _filter_outdated_snapshots(
    models_list: list[dict[str, Any]],
    provider_label: str,
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    """Keep undated aliases plus latest dated snapshot per family.

    Returns filtered models and explicit deactivation reasons for stale snapshots.
    """
    families: dict[str, list[tuple[dict[str, Any], object]]] = {}
    for entry in models_list:
        model_id = (entry.get("model_id") or "").strip()
        if not model_id:
            continue
        family = _model_family_key(model_id)
        snapshot_date = _extract_snapshot_date(model_id)
        families.setdefault(family, []).append((entry, snapshot_date))

    kept_entries: list[dict[str, Any]] = []
    explicit_reasons: dict[str, tuple[str, str]] = {}

    for members in families.values():
        undated = [(m, d) for m, d in members if d is None]
        dated = [(m, d) for m, d in members if d is not None]

        for model, _ in undated:
            kept_entries.append(model)

        if not dated:
            continue

        dated_sorted = sorted(dated, key=lambda item: item[1], reverse=True)
        latest_model, latest_date = dated_sorted[0]
        kept_entries.append(latest_model)

        latest_id = latest_model.get("model_id") or "latest snapshot"
        latest_date_text = latest_date.isoformat() if latest_date else "unknown date"
        for stale_model, stale_date in dated_sorted[1:]:
            stale_id = stale_model.get("model_id")
            if not stale_id:
                continue
            stale_date_text = stale_date.isoformat() if stale_date else "unknown date"
            explicit_reasons[stale_id] = (
                f"Filtered outdated snapshot from live {provider_label} catalog.",
                f"outdated_snapshot: {stale_id} ({stale_date_text}) superseded by {latest_id} ({latest_date_text})",
            )

    return kept_entries, explicit_reasons


def _infer_model_capabilities(model_id: str, supported_methods: Optional[list[str]] = None, modalities: Any = None) -> dict:
    normalized = (model_id or "").lower()
    methods = {m.lower() for m in (supported_methods or []) if isinstance(m, str)}
    modality_text = " ".join(modalities) if isinstance(modalities, list) else str(modalities or "")
    modality_text = modality_text.lower()

    if "embed" in normalized or "embedcontent" in methods:
        return {"embedding": True}

    if any(token in normalized for token in ("moderation", "whisper", "transcribe", "transcription", "tts", "speech")):
        return {"audio_or_moderation": True}

    if any(token in normalized for token in ("babbage", "davinci")):
        return {"legacy_completion": True}

    if any(token in normalized for token in ("imagen", "dall-e", "flux", "stable-diffusion", "sdxl", "gpt-image", "chatgpt-image")):
        return {"image_generation": True}

    capabilities: dict[str, bool] = {"chat": True, "streaming": True}
    if any(token in normalized for token in ("codex", "coder", "copilot", "code", "starcoder")):
        capabilities["code"] = True
    if "vision" in normalized or "image" in modality_text or "vision" in modality_text:
        capabilities["vision"] = True
    if "generatecontent" in methods or "counttokens" in methods:
        capabilities["chat"] = True
    return capabilities


def _is_catalog_usable(model_id: str, capabilities: dict[str, Any]) -> bool:
    normalized = (model_id or "").lower()
    if capabilities.get("embedding") or capabilities.get("audio_or_moderation") or capabilities.get("legacy_completion"):
        return False
    if any(token in normalized for token in ("moderation", "whisper", "transcribe", "transcription", "tts", "speech", "babbage", "davinci")):
        return False
    return bool(
        capabilities.get("chat")
        or capabilities.get("image_generation")
        or capabilities.get("vision")
        or capabilities.get("code")
    )


def _enrich_with_litellm_metadata(provider_name: str, model_entry: dict[str, Any]) -> dict[str, Any]:
    litellm_model = _build_litellm_model(provider_name, model_entry["model_id"])
    try:
        import litellm

        info = litellm.get_model_info(litellm_model)
    except Exception:
        return model_entry

    context_window = info.get("max_input_tokens") or info.get("max_tokens")
    output_tokens = info.get("max_output_tokens") or info.get("max_tokens")
    input_cost = info.get("input_cost_per_token")
    output_cost = info.get("output_cost_per_token")
    capabilities = model_entry.get("caps") or {}

    if info.get("supports_vision"):
        capabilities["vision"] = True
    if info.get("supports_function_calling"):
        capabilities["function_calling"] = True
    if info.get("mode") == "chat":
        capabilities["chat"] = True
        capabilities["streaming"] = True

    if model_entry.get("ctx") is None and context_window:
        model_entry["ctx"] = int(context_window)
    if model_entry.get("max_output_tokens") is None and output_tokens:
        model_entry["max_output_tokens"] = int(output_tokens)
    if model_entry.get("input") is None and input_cost is not None:
        model_entry["input"] = round(float(input_cost) * 1_000_000, 6)
    if model_entry.get("output") is None and output_cost is not None:
        model_entry["output"] = round(float(output_cost) * 1_000_000, 6)
    model_entry["caps"] = capabilities
    return model_entry


async def _fetch_openrouter_models() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        payload = response.json()

    discovered: list[dict[str, Any]] = []
    for item in payload.get("data", []):
        model_id = (item.get("id") or "").strip()
        if not model_id:
            continue
        pricing = item.get("pricing") or {}
        entry = {
            "model_id": model_id,
            "display_name": item.get("name") or _humanize_model_id(model_id),
            "input": (_safe_float(pricing.get("input")) or 0.0) * 1_000_000 if pricing.get("input") is not None else None,
            "output": (_safe_float(pricing.get("output")) or 0.0) * 1_000_000 if pricing.get("output") is not None else None,
            "ctx": _safe_int(item.get("context_length")),
            "caps": _infer_model_capabilities(model_id, modalities=item.get("architecture", {}).get("modality")),
        }
        enriched = _mark_catalog_entry_viability(_enrich_with_litellm_metadata("openrouter", entry), item, "OpenRouter")
        if _is_catalog_usable(model_id, enriched.get("caps") or {}):
            discovered.append(enriched)
    return discovered


async def _fetch_openai_compatible_models(base_url: str, api_key: str, provider_name: str, extra_headers: Optional[dict[str, str]] = None) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {api_key}"}
    if extra_headers:
        headers.update(extra_headers)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
        payload = response.json()

    # For Copilot, derive a provider suffix to keep models distinguishable in the UI.
    _provider_suffix = " (GitHub Copilot)" if provider_name == "github-copilot" else ""

    discovered: list[dict[str, Any]] = []
    for item in payload.get("data", []):
        model_id = (item.get("id") or "").strip()
        if not model_id:
            continue

        # Use the API's own name/display_name field when present; fall back to humanised model_id.
        raw_name = (item.get("name") or item.get("display_name") or "").strip()
        display_name = (raw_name + _provider_suffix) if raw_name else (_humanize_model_id(model_id) + _provider_suffix)

        # For Copilot models, also pull context/output limits from the capabilities block.
        _caps_block = item.get("capabilities") or {}
        _limits = _caps_block.get("limits") or {}
        ctx_from_api = _limits.get("max_context_window_tokens") or _limits.get("max_prompt_tokens")
        max_output_from_api = _limits.get("max_output_tokens") or _limits.get("max_non_streaming_output_tokens")

        entry = {
            "model_id": model_id,
            "display_name": display_name,
            "input": None,
            "output": None,
            "ctx": ctx_from_api,
            "max_output_tokens": max_output_from_api,
            "caps": _infer_model_capabilities(model_id),
        }
        enriched = _mark_catalog_entry_viability(
            _enrich_with_litellm_metadata(provider_name, entry),
            item,
            provider_name,
        )
        if _is_catalog_usable(model_id, enriched.get("caps") or {}):
            discovered.append(enriched)
    return discovered


async def _fetch_google_models(api_key: str) -> list[dict[str, Any]]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()

    discovered: list[dict[str, Any]] = []
    for item in payload.get("models", []):
        raw_name = (item.get("name") or "").strip()
        model_id = raw_name.split("/", 1)[-1] if raw_name else ""
        if not model_id:
            continue
        supported_methods = item.get("supportedGenerationMethods") or []
        entry = {
            "model_id": model_id,
            "display_name": item.get("displayName") or _humanize_model_id(model_id),
            "input": None,
            "output": None,
            "ctx": _safe_int(item.get("inputTokenLimit")),
            "caps": _infer_model_capabilities(model_id, supported_methods=supported_methods),
            "max_output_tokens": _safe_int(item.get("outputTokenLimit")),
        }
        enriched = _mark_catalog_entry_viability(_enrich_with_litellm_metadata("google", entry), item, "Google")
        if _is_catalog_usable(model_id, enriched.get("caps") or {}):
            discovered.append(enriched)
    return discovered


async def _fetch_anthropic_models(api_key: str) -> list[dict[str, Any]]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get("https://api.anthropic.com/v1/models", headers=headers)
        response.raise_for_status()
        payload = response.json()

    discovered: list[dict[str, Any]] = []
    for item in payload.get("data", []):
        model_id = (item.get("id") or "").strip()
        if not model_id:
            continue
        entry = {
            "model_id": model_id,
            "display_name": item.get("display_name") or _humanize_model_id(model_id),
            "input": None,
            "output": None,
            "ctx": None,
            "caps": _infer_model_capabilities(model_id),
        }
        enriched = _mark_catalog_entry_viability(_enrich_with_litellm_metadata("anthropic", entry), item, "Anthropic")
        if _is_catalog_usable(model_id, enriched.get("caps") or {}):
            discovered.append(enriched)
    return discovered


async def discover_provider_models(provider_name: str) -> tuple[list[dict[str, Any]], str]:
    normalized = (provider_name or "").lower().strip()

    if normalized == "openrouter":
        return await _fetch_openrouter_models(), "provider_api"

    if normalized == "openai":
        api_key = get_provider_api_key("openai")
        if api_key:
            return await _fetch_openai_compatible_models("https://api.openai.com/v1", api_key, "openai"), "provider_api"

    if normalized == "google":
        api_key = get_provider_api_key("google")
        if api_key:
            return await _fetch_google_models(api_key), "provider_api"

    if normalized == "anthropic":
        api_key = get_provider_api_key("anthropic")
        if api_key:
            return await _fetch_anthropic_models(api_key), "provider_api"

    if normalized == "openai-codex":
        api_key = get_provider_api_key("openai-codex")
        if should_use_codex_oauth_proxy("openai-codex", api_key=api_key):
            return await _fetch_openai_compatible_models(get_codex_proxy_base_url(), get_codex_proxy_api_key(), "openai-codex"), "codex_proxy"
        if api_key:
            return await _fetch_openai_compatible_models("https://api.openai.com/v1", api_key, "openai-codex"), "provider_api"

    if normalized == "github-copilot":
        github_token = (get_first_github_token() or "").strip()
        if github_token:
            return await _fetch_openai_compatible_models(COPILOT_API_BASE, github_token, "github-copilot", extra_headers=get_copilot_headers()), "provider_api"

    fallback_models = [dict(model) for model in PROVIDER_DEFAULT_MODELS.get(normalized, [])]
    enriched_fallback = [_enrich_with_litellm_metadata(normalized, entry) for entry in fallback_models]
    return enriched_fallback, "static_catalog"


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


def _qualified_model_ref(provider_name: str, model_id: str) -> str:
    """Return provider-qualified model reference for logging and diagnostics."""
    return f"{(provider_name or 'unknown').strip()}/{(model_id or '').strip()}"


# ---------------------------------------------------------------------------
# Core sync logic (shared by endpoint + startup)
# ---------------------------------------------------------------------------

async def run_model_sync(db: AsyncSession, *, deduplicate_existing: bool = True) -> dict:
    """
    Sync Ollama models + enabled paid providers into the DB.
    Returns a summary dict.
    """
    added = []
    skipped = []
    errors = []
    provider_details: dict[str, dict[str, Any]] = {}

    def mark_model_unavailable(
        current: Model,
        *,
        warning: str,
        validation_source: str,
        validation_error: Optional[str] = None,
    ) -> None:
        current.is_active = False
        current.validation_status = "failed"
        current.validation_source = validation_source
        current.validation_warning = warning
        current.validation_error = validation_error

    def deactivate_provider_models(
        provider: Provider,
        *,
        warning: str,
        validation_source: str,
        validation_error: Optional[str] = None,
        keep_discovered_ids: Optional[set[str]] = None,
        explicit_reasons: Optional[dict[str, tuple[str, Optional[str]]]] = None,
    ) -> int:
        deactivated = 0
        keep_discovered_ids = keep_discovered_ids or set()
        explicit_reasons = explicit_reasons or {}
        for (provider_id, existing_model_id), current in existing.items():
            if provider_id != str(provider.id):
                continue
            if existing_model_id in keep_discovered_ids:
                continue
            reason_warning, reason_error = explicit_reasons.get(existing_model_id, (warning, validation_error))
            mark_model_unavailable(
                current,
                warning=reason_warning,
                validation_source=validation_source,
                validation_error=reason_error,
            )
            deactivated += 1
        return deactivated

    async def deduplicate_models() -> int:
        result = await db.execute(select(Model))
        all_models = list(result.scalars().all())
        grouped: dict[tuple[str, str], list[Model]] = {}
        for model in all_models:
            grouped.setdefault((str(model.provider_id), model.model_id), []).append(model)

        duplicates_removed = 0
        for _, group in grouped.items():
            if len(group) < 2:
                continue

            group.sort(
                key=lambda item: (
                    0 if (item.validation_status or "") == "validated" else 1,
                    0 if item.is_active else 1,
                    item.created_at or datetime.min,
                    str(item.id),
                )
            )
            canonical = group[0]

            for duplicate in group[1:]:
                await db.execute(
                    update(Persona)
                    .where(Persona.primary_model_id == duplicate.id)
                    .values(primary_model_id=canonical.id)
                )
                await db.execute(
                    update(Persona)
                    .where(Persona.fallback_model_id == duplicate.id)
                    .values(fallback_model_id=canonical.id)
                )
                await db.execute(
                    update(Message)
                    .where(Message.model_used == duplicate.id)
                    .values(model_used=canonical.id)
                )
                await db.execute(
                    update(RequestLog)
                    .where(RequestLog.model_id == duplicate.id)
                    .values(model_id=canonical.id)
                )
                await db.execute(
                    update(Agent)
                    .where(Agent.model_id == duplicate.id)
                    .values(model_id=canonical.id)
                )
                await db.execute(delete(Model).where(Model.id == duplicate.id))
                duplicates_removed += 1

        if duplicates_removed:
            await db.flush()
        return duplicates_removed

    # ── ensure providers exist ────────────────────────────────────────────────
    all_providers_result = await db.execute(select(Provider))
    providers_by_name: dict[str, Provider] = {
        p.name: p for p in all_providers_result.scalars().all()
    }

    async def get_or_create_provider(name: str, display: str, api_base: str, auth_type: str) -> Provider:
        if name in providers_by_name:
            existing_provider = providers_by_name[name]
            existing_provider.display_name = display
            existing_provider.api_base_url = api_base
            existing_provider.auth_type = auth_type
            existing_provider.is_active = True
            return existing_provider
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

    duplicates_removed = 0
    if deduplicate_existing:
        duplicates_removed = await deduplicate_models()

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
        *,
        validation_status: str,
        validation_source: str,
        validation_warning: Optional[str] = None,
    ) -> bool:
        """Upsert a model. Returns True if it was new."""
        key = (str(provider.id), model_id)
        qualified_ref = _qualified_model_ref(provider.name, model_id)
        if key in existing:
            current = existing[key]
            # Re-activate models that are back in the live catalog (may have been
            # deactivated by a previous sync that saw fewer models from the API).
            current.is_active = True
            current.validation_error = None
            # Always update the display name so freshly generated names (e.g.
            # "Gpt 5 5") get replaced by a proper name on the next sync.
            if display_name:
                current.display_name = display_name
            current.cost_per_1m_input = current.cost_per_1m_input if current.cost_per_1m_input is not None else cost_in
            current.cost_per_1m_output = current.cost_per_1m_output if current.cost_per_1m_output is not None else cost_out
            current.context_window = current.context_window or ctx
            current.capabilities = current.capabilities or caps
            if validation_status == "validated":
                current.validation_status = "validated"
                current.validated_at = datetime.utcnow()
                current.validation_source = validation_source
                current.validation_warning = validation_warning
            elif (current.validation_status or "unverified") != "validated":
                current.validation_status = validation_status
                current.validation_source = validation_source
                current.validation_warning = validation_warning
            logger.debug("Model sync upsert existing: %s", qualified_ref)
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
            validation_status=validation_status,
            validated_at=datetime.utcnow() if validation_status == "validated" else None,
            validation_source=validation_source,
            validation_warning=validation_warning,
            validation_error=None,
        )
        db.add(m)
        existing[key] = m
        logger.info("Model sync upsert new: %s", qualified_ref)
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

            if upsert_model(
                ollama_provider, model_id, display, 0.0, 0.0, ctx_window, caps,
                validation_status="validated",
                validation_source="ollama_sync",
            ):
                added.append(f"ollama/{model_id}")
            else:
                skipped.append(f"ollama/{model_id}")
        logger.info(f"Ollama sync: {len(ollama_raw)} models found")
    else:
        logger.info("Ollama not reachable — skipping local model sync")

    # ── 2. Paid providers (key-gated) ─────────────────────────────────────────
    for provider_name in PROVIDER_DEFAULT_MODELS:
        if not has_provider_api_key(provider_name):
            logger.debug(f"Skipping {provider_name} — no API key set")
            deactivated_missing = 0
            existing_provider = providers_by_name.get(provider_name)
            if existing_provider:
                existing_provider.is_active = False
                deactivated_missing = deactivate_provider_models(
                    existing_provider,
                    warning="Provider is not currently configured, so this model is unavailable.",
                    validation_source="provider_sync:unavailable",
                    validation_error="provider_not_configured",
                )
            provider_details[provider_name] = {
                "configured": False,
                "source": "unavailable",
                "discovered": 0,
                "added": 0,
                "skipped": 0,
                "deactivated": deactivated_missing,
            }
            continue

        display_name, api_base, auth_type = PROVIDER_SYNC_META[provider_name]
        provider = await get_or_create_provider(provider_name, display_name, api_base, auth_type)

        provider_added = 0
        provider_skipped = 0
        models_list: list[dict[str, Any]] = []
        source = "static_catalog"
        outdated_skipped = 0
        try:
            models_list, source = await discover_provider_models(provider_name)
        except Exception as exc:
            logger.warning("Live model discovery failed for provider %s: %s", provider_name, exc)
            errors.append(f"{provider_name}: {type(exc).__name__}: {exc}")
            models_list = [_enrich_with_litellm_metadata(provider_name, dict(model)) for model in PROVIDER_DEFAULT_MODELS[provider_name]]

        if source in {"provider_api", "codex_proxy"}:
            provider_label = provider.display_name or provider_name
            original_count = len(models_list)
            models_list, outdated_reasons = _filter_outdated_snapshots(models_list, provider_label)
            explicit_deactivation_reasons = dict(outdated_reasons)
            outdated_skipped = max(0, original_count - len(models_list))
        else:
            explicit_deactivation_reasons = {}

        provider.config = {
            **(provider.config or {}),
            "last_sync_source": source,
            "last_sync_model_count": len(models_list),
            "last_synced_at": datetime.utcnow().isoformat(),
        }
        provider.is_active = True

        discovered_refs = [
            _qualified_model_ref(provider_name, m.get("model_id", ""))
            for m in models_list
            if m.get("model_id")
        ]
        logger.info(
            "Discovered %d model(s) for provider %s via %s (examples: %s)",
            len(discovered_refs),
            provider_name,
            source,
            ", ".join(discovered_refs[:10]) if discovered_refs else "none",
        )

        viable_discovered_ids: set[str] = set()
        deprecated_skipped = 0

        for m in models_list:
            is_viable, viability_warning, viability_error = get_catalog_model_viability(m)
            if not is_viable:
                if m.get("model_id"):
                    explicit_deactivation_reasons[m["model_id"]] = (
                        viability_warning or "Model is no longer viable.",
                        viability_error,
                    )
                deprecated_skipped += 1
                continue

            viable_discovered_ids.add(m["model_id"])
            if upsert_model(
                provider, m["model_id"], m["display_name"],
                m.get("input") or 0.0, m.get("output") or 0.0, m.get("ctx"), m.get("caps") or {"chat": True, "streaming": True},
                validation_status="unverified",
                validation_source=f"provider_sync:{source}",
                validation_warning=(
                    "Provider is configured, but this model has not been live-validated in the interface yet."
                    if source != "provider_api" else
                    "Discovered from the provider catalog, but not yet live-validated in the interface."
                ),
            ):
                added.append(f"{provider_name}/{m['model_id']}")
                provider_added += 1
            else:
                skipped.append(f"{provider_name}/{m['model_id']}")
                provider_skipped += 1

        deactivated_missing = 0
        deleted_stale = 0
        if source in {"provider_api", "codex_proxy"}:
            provider_label = provider.display_name or provider_name
            validation_error = "model_not_supported" if provider_name == "github-copilot" else "model_not_in_live_catalog"
            deactivated_missing = deactivate_provider_models(
                provider,
                keep_discovered_ids=viable_discovered_ids,
                warning=f"This model is no longer exposed by the live {provider_label} catalog.",
                validation_source=f"provider_sync:{source}",
                validation_error=validation_error,
                explicit_reasons=explicit_deactivation_reasons,
            )

            # Purge stale models: hard-delete inactive models no longer
            # in the live catalog that are not referenced by any Persona or Agent.
            inactive_ids = [
                m.id for (prov_id, _mid), m in existing.items()
                if prov_id == str(provider.id) and not m.is_active
            ]
            if inactive_ids:
                persona_res = await db.execute(
                    select(Persona.primary_model_id, Persona.fallback_model_id).where(
                        (Persona.primary_model_id.in_(inactive_ids)) |
                        (Persona.fallback_model_id.in_(inactive_ids))
                    )
                )
                referenced: set[str] = set()
                for row in persona_res:
                    if row[0] is not None:
                        referenced.add(str(row[0]))
                    if row[1] is not None:
                        referenced.add(str(row[1]))

                agent_res = await db.execute(
                    select(Agent.model_id).where(Agent.model_id.in_(inactive_ids))
                )
                for row in agent_res:
                    if row[0] is not None:
                        referenced.add(str(row[0]))

                deletable_ids = [mid for mid in inactive_ids if str(mid) not in referenced]
                if deletable_ids:
                    await db.execute(delete(Model).where(Model.id.in_(deletable_ids)))
                    del_id_strs = {str(d) for d in deletable_ids}
                    stale_keys = [k for k, m in existing.items() if str(m.id) in del_id_strs]
                    for k in stale_keys:
                        del existing[k]
                    deleted_stale = len(deletable_ids)
                    logger.info(
                        "Purged %d stale model(s) for provider %s (not in live catalog, unreferenced)",
                        deleted_stale, provider_name,
                    )

        provider_details[provider_name] = {
            "configured": True,
            "source": source,
            "discovered": len(models_list),
            "added": provider_added,
            "skipped": provider_skipped,
            "deprecated_skipped": deprecated_skipped,
            "outdated_skipped": outdated_skipped,
            "deactivated": deactivated_missing,
            "deleted_stale": deleted_stale,
        }

    await db.commit()

    summary = {
        "added": added,
        "skipped_existing": len(skipped),
        "errors": errors,
        "ollama_available": len(ollama_raw) > 0,
        "ollama_models": len([a for a in added if a.startswith("ollama/")]),
        "paid_models": len([a for a in added if not a.startswith("ollama/")]),
        "provider_details": provider_details,
        "duplicates_removed": duplicates_removed,
        "stale_deleted": sum(d.get("deleted_stale", 0) for d in provider_details.values()),
    }
    logger.info(
        "Model sync complete: %d added, %d already existed (added examples: %s)",
        len(added),
        len(skipped),
        ", ".join(added[:10]) if added else "none",
    )
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
    for name in PROVIDER_DEFAULT_MODELS:
        providers_status[name] = has_provider_api_key(name)

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
                "sync_mode": "live_discovery_with_fallback",
            }
            for name, has_key in providers_status.items()
        },
    }


@router.post("/cleanup")
async def cleanup_and_resync(db: AsyncSession = Depends(get_db)):
    """
    DESTRUCTIVE OPERATION: Deletes all models from the database and re-syncs from provider catalogs.

    This removes junk/stale models and starts fresh. All references to deleted models
    (in personas, agents, request logs) will be set to NULL.

    Returns: Summary of deleted models and fresh sync results.
    """
    logger.warning("=== DESTRUCTIVE MODEL CLEANUP STARTING ===")

    # Get model counts before deletion
    result = await db.execute(select(Model))
    models_before = len(list(result.scalars().all()))

    # Delete all models (cascading will handle cleanup)
    result = await db.execute(delete(Model))
    deleted_count = result.rowcount

    # Also reset all providers to start fresh
    result_providers = await db.execute(select(Provider))
    for provider in result_providers.scalars().all():
        provider.config = {}
        provider.is_active = True

    await db.flush()
    logger.warning(f"Deleted {deleted_count} models from database")

    # Now run fresh sync
    try:
        sync_result = await run_model_sync(db, deduplicate_existing=False)
        logger.info(f"Fresh sync complete after cleanup: {len(sync_result['added'])} models added")

        return {
            "ok": True,
            "cleanup": {
                "deleted_models": deleted_count,
                "models_before": models_before,
            },
            "fresh_sync": sync_result,
            "message": f"Cleanup complete. {deleted_count} junk models removed. Fresh sync added {len(sync_result['added'])} active models.",
        }
    except Exception as e:
        logger.error(f"Fresh sync failed after cleanup: {e}")
        await db.rollback()
        return {
            "ok": False,
            "error": f"Cleanup succeeded ({deleted_count} models deleted) but fresh sync failed: {str(e)}",
            "cleanup": {
                "deleted_models": deleted_count,
                "models_before": models_before,
            },
        }
