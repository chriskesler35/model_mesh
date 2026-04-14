"""Helpers for the local Codex CLI OAuth proxy integration."""

from __future__ import annotations

import json
import os
import shutil
import socket
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


DEFAULT_CODEX_PROXY_BASE_URL = "http://127.0.0.1:10531/v1"
CODEX_PROXY_PROVIDERS = {"openai", "openai-codex"}
CODEX_PROXY_API_KEY_PLACEHOLDER = "codex-oauth"
OPENAI_OAUTH_ACCESS_TOKEN_ENV = "OPENAI_OAUTH_ACCESS_TOKEN"
OPENAI_OAUTH_REFRESH_TOKEN_ENV = "OPENAI_OAUTH_REFRESH_TOKEN"
SUPPORTED_CODEX_PROXY_SCHEMES = {"http", "https"}
_CODEX_PROXY_HEALTH_CACHE: dict[str, float | bool] = {"checked_at": 0.0, "reachable": False}


def get_codex_auth_file() -> Path:
    raw = os.environ.get("CODEX_AUTH_FILE")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".codex" / "auth.json"


def has_codex_cli_auth() -> bool:
    if os.environ.get(OPENAI_OAUTH_ACCESS_TOKEN_ENV) or os.environ.get(OPENAI_OAUTH_REFRESH_TOKEN_ENV):
        return True

    auth_file = get_codex_auth_file()
    if not auth_file.exists():
        return False

    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
    except Exception:
        return False

    tokens = data.get("tokens") or {}
    return bool(tokens.get("access_token") or tokens.get("refresh_token"))


def get_codex_oauth_tokens() -> dict[str, Optional[str]]:
    access_token = (os.environ.get(OPENAI_OAUTH_ACCESS_TOKEN_ENV) or "").strip() or None
    refresh_token = (os.environ.get(OPENAI_OAUTH_REFRESH_TOKEN_ENV) or "").strip() or None

    auth_file = get_codex_auth_file()
    if auth_file.exists():
        try:
            data = json.loads(auth_file.read_text(encoding="utf-8"))
            tokens = data.get("tokens") or {}
            access_token = access_token or tokens.get("access_token")
            refresh_token = refresh_token or tokens.get("refresh_token")
        except Exception:
            pass

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "auth_file": str(auth_file),
    }


def write_codex_cli_auth(access_token: Optional[str] = None, refresh_token: Optional[str] = None) -> Path:
    auth_file = get_codex_auth_file()
    auth_file.parent.mkdir(parents=True, exist_ok=True)

    payload: dict = {}
    if auth_file.exists():
        try:
            payload = json.loads(auth_file.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}

    if access_token is not None:
        clean_access_token = access_token.strip()
        if clean_access_token:
            tokens["access_token"] = clean_access_token
        else:
            tokens.pop("access_token", None)

    if refresh_token is not None:
        clean_refresh_token = refresh_token.strip()
        if clean_refresh_token:
            tokens["refresh_token"] = clean_refresh_token
        else:
            tokens.pop("refresh_token", None)

    payload["tokens"] = tokens
    auth_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return auth_file


def get_codex_proxy_base_url() -> str:
    return (os.environ.get("CODEX_OAUTH_PROXY_BASE_URL") or DEFAULT_CODEX_PROXY_BASE_URL).rstrip("/")


def get_codex_proxy_scheme() -> str:
    return (urlparse(get_codex_proxy_base_url()).scheme or "http").lower()


def codex_proxy_url_is_supported() -> bool:
    return get_codex_proxy_scheme() in SUPPORTED_CODEX_PROXY_SCHEMES


def is_default_codex_proxy_base_url() -> bool:
    return get_codex_proxy_base_url().rstrip("/") == DEFAULT_CODEX_PROXY_BASE_URL.rstrip("/")


def get_codex_proxy_configuration_issue() -> Optional[str]:
    base_url = get_codex_proxy_base_url()
    scheme = get_codex_proxy_scheme()

    if scheme not in SUPPORTED_CODEX_PROXY_SCHEMES:
        return (
            f"Configured Codex proxy URL uses unsupported scheme '{scheme}'. "
            "Model Mesh requires an OpenAI-compatible http(s) base URL."
        )

    if is_default_codex_proxy_base_url() and shutil.which("codex") and not is_codex_proxy_reachable(cache_ttl_seconds=0):
        return (
            "The installed Codex CLI does not expose the default OpenAI-compatible HTTP proxy "
            f"at {base_url}. Its app-server uses stdio or websocket transports instead."
        )

    return None


def is_codex_proxy_reachable(timeout: float = 0.35, cache_ttl_seconds: float = 5.0) -> bool:
    """Return whether the local Codex OAuth proxy is currently reachable."""
    if not codex_proxy_url_is_supported():
        _CODEX_PROXY_HEALTH_CACHE["checked_at"] = time.monotonic()
        _CODEX_PROXY_HEALTH_CACHE["reachable"] = False
        return False

    now = time.monotonic()
    cached_at = float(_CODEX_PROXY_HEALTH_CACHE.get("checked_at", 0.0) or 0.0)
    if now - cached_at < cache_ttl_seconds:
        return bool(_CODEX_PROXY_HEALTH_CACHE.get("reachable"))

    parsed = urlparse(get_codex_proxy_base_url())
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    reachable = False

    if host:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                reachable = True
        except OSError:
            reachable = False

    _CODEX_PROXY_HEALTH_CACHE["checked_at"] = now
    _CODEX_PROXY_HEALTH_CACHE["reachable"] = reachable
    return reachable


def provider_supports_codex_oauth(provider_name: str) -> bool:
    return (provider_name or "").lower().strip() in CODEX_PROXY_PROVIDERS


def should_use_codex_oauth_proxy(provider_name: str, api_key: str | None = None) -> bool:
    normalized = (provider_name or "").lower().strip()
    if not provider_supports_codex_oauth(normalized):
        return False
    if not has_codex_cli_auth():
        return False
    if not codex_proxy_url_is_supported():
        return False
    if not is_codex_proxy_reachable():
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
