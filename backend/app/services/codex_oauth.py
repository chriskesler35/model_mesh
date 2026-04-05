"""Helpers for the local Codex CLI OAuth proxy integration."""

from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_CODEX_PROXY_BASE_URL = "http://127.0.0.1:10531/v1"
CODEX_PROXY_PROVIDERS = {"openai", "openai-codex"}
CODEX_PROXY_API_KEY_PLACEHOLDER = "codex-oauth"


def get_codex_auth_file() -> Path:
    raw = os.environ.get("CODEX_AUTH_FILE")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".codex" / "auth.json"


def has_codex_cli_auth() -> bool:
    auth_file = get_codex_auth_file()
    if not auth_file.exists():
        return False

    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
    except Exception:
        return False

    tokens = data.get("tokens") or {}
    return bool(tokens.get("access_token") or tokens.get("refresh_token"))


def get_codex_proxy_base_url() -> str:
    return (os.environ.get("CODEX_OAUTH_PROXY_BASE_URL") or DEFAULT_CODEX_PROXY_BASE_URL).rstrip("/")


def provider_supports_codex_oauth(provider_name: str) -> bool:
    return (provider_name or "").lower().strip() in CODEX_PROXY_PROVIDERS


def should_use_codex_oauth_proxy(provider_name: str, api_key: str | None = None) -> bool:
    normalized = (provider_name or "").lower().strip()
    if not provider_supports_codex_oauth(normalized):
        return False
    if not has_codex_cli_auth():
        return False
    # The dedicated Codex provider should always honor the local OAuth-backed
    # proxy so it behaves like the user's VS Code / Codex CLI session.
    if normalized == "openai-codex":
        return True
    # When the user sets PREFER_CODEX_OAUTH=1, route plain OpenAI models
    # through the OAuth proxy even if an API key is set. Useful when your
    # sk- key is dead/unfunded but you want ChatGPT Plus OAuth to do the work.
    if os.environ.get("PREFER_CODEX_OAUTH", "").strip().lower() in ("1", "true", "yes"):
        return True
    # Plain OpenAI dual-mode: prefer a real API key when present,
    # otherwise fall back to the local OAuth proxy.
    return not bool(api_key)


def codex_proxy_rejects_temperature(model_id: str) -> bool:
    normalized = (model_id or "").lower().strip()
    return (
        "codex" in normalized
        or normalized.startswith(("gpt-5", "o1", "o3", "o4"))
    )


def get_codex_proxy_api_key() -> str:
    return CODEX_PROXY_API_KEY_PLACEHOLDER
