"""Runtime provider capability snapshot helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.routes.model_sync import discover_provider_models
from app.services.oauth_providers import get_provider_registry
from app.services.provider_credentials import has_provider_api_key


_CAPABILITY_CACHE: dict[str, Any] = {
    "checked_at": None,
    "payload": None,
}
_CACHE_TTL_SECONDS = 300


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_provider_capability_snapshot() -> dict[str, Any]:
    """Return provider capability metadata for diagnostics and routing.

    Notes:
    - `has_credentials` indicates a runtime key/token is currently available.
    - `oauth_configured` indicates OAuth app credentials are configured.
    - `auto_model_routing_exposed` indicates whether a provider advertises a
      first-party auto-routing mode in our current integration.
    """
    registry = get_provider_registry()

    providers: dict[str, dict[str, Any]] = {
        "anthropic": {
            "has_credentials": has_provider_api_key("anthropic"),
            "oauth_configured": False,
            "auto_model_routing_exposed": False,
        },
        "google": {
            "has_credentials": has_provider_api_key("google") or has_provider_api_key("gemini"),
            "oauth_configured": "google" in registry,
            "auto_model_routing_exposed": False,
        },
        "openrouter": {
            "has_credentials": has_provider_api_key("openrouter"),
            "oauth_configured": False,
            "auto_model_routing_exposed": True,
        },
        "openai": {
            "has_credentials": has_provider_api_key("openai"),
            "oauth_configured": False,
            "auto_model_routing_exposed": False,
        },
        "openai-codex": {
            "has_credentials": has_provider_api_key("openai-codex"),
            "oauth_configured": bool(settings.openai_api_key),
            "auto_model_routing_exposed": False,
        },
        "github-copilot": {
            "has_credentials": has_provider_api_key("github-copilot"),
            "oauth_configured": bool(settings.github_client_id and settings.github_client_secret),
            "auto_model_routing_exposed": False,
        },
    }

    now = datetime.now(timezone.utc)
    cached_ts = _CAPABILITY_CACHE.get("checked_at")
    if isinstance(cached_ts, datetime):
        age = (now - cached_ts).total_seconds()
        if age <= _CACHE_TTL_SECONDS and _CAPABILITY_CACHE.get("payload"):
            return _CAPABILITY_CACHE["payload"]

    async def _probe(provider_name: str, provider_entry: dict[str, Any]) -> dict[str, Any]:
        result = dict(provider_entry)
        if not provider_entry.get("has_credentials"):
            result.update(
                {
                    "catalog_source": "not_available",
                    "model_count": 0,
                    "sample_models": [],
                    "probe_error": None,
                }
            )
            return result
        try:
            models, source = await discover_provider_models(provider_name)
            sample_models = [m.get("model_id") for m in models[:10] if m.get("model_id")]
            result.update(
                {
                    "catalog_source": source,
                    "model_count": len(models),
                    "sample_models": sample_models,
                    "probe_error": None,
                }
            )
            return result
        except Exception as exc:
            result.update(
                {
                    "catalog_source": "error",
                    "model_count": 0,
                    "sample_models": [],
                    "probe_error": str(exc),
                }
            )
            return result

    probes = await asyncio.gather(*[_probe(name, info) for name, info in providers.items()])
    provider_snapshot = {name: payload for name, payload in zip(providers.keys(), probes)}

    response = {
        "checked_at": _utc_now_iso(),
        "cache_ttl_seconds": _CACHE_TTL_SECONDS,
        "providers": provider_snapshot,
        "features": {
            "model_routing_auto_enabled": bool(settings.model_routing_auto_enabled),
        },
    }

    _CAPABILITY_CACHE["checked_at"] = now
    _CAPABILITY_CACHE["payload"] = response

    return response
