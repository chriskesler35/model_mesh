"""Shared live credential helpers for provider-backed features.

OAuth-connected keys and manually entered API keys are both stored as provider
credentials. These helpers make sure runtime reads come from the current live
state first, while still supporting the startup-loaded settings snapshot.
"""

from __future__ import annotations

import os
from typing import Optional

from app.config import settings
from app.services.codex_oauth import (
    has_codex_cli_auth,
    is_codex_proxy_reachable,
    provider_supports_codex_oauth,
)


PROVIDER_ENV_VARS: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "openai-codex": ("OPENAI_API_KEY",),
    "ollama": (),
}

PROVIDER_SETTING_ATTRS: dict[str, tuple[str, ...]] = {
    "anthropic": ("anthropic_api_key",),
    "google": ("gemini_api_key", "google_api_key"),
    "gemini": ("gemini_api_key", "google_api_key"),
    "openrouter": ("openrouter_api_key",),
    "openai": ("openai_api_key",),
    "openai-codex": ("openai_api_key",),
    "ollama": (),
}


def get_provider_env_vars(provider_name: str) -> tuple[str, ...]:
    return PROVIDER_ENV_VARS.get((provider_name or "").lower().strip(), ())


def get_provider_setting_attrs(provider_name: str) -> tuple[str, ...]:
    return PROVIDER_SETTING_ATTRS.get((provider_name or "").lower().strip(), ())


def get_provider_api_key(provider_name: str) -> Optional[str]:
    """Return the active live credential for a provider, if any."""
    for env_var in get_provider_env_vars(provider_name):
        value = os.environ.get(env_var)
        if value:
            return value

    for attr in get_provider_setting_attrs(provider_name):
        value = getattr(settings, attr, None)
        if value:
            return value

    return None


def has_provider_api_key(provider_name: str) -> bool:
    normalized = (provider_name or "").lower().strip()
    if provider_supports_codex_oauth(normalized):
        if get_provider_api_key(normalized):
            return True
        return has_codex_cli_auth() and is_codex_proxy_reachable()
    if normalized == "github-copilot":
        # Copilot uses a GitHub OAuth token stored on a user record
        from app.services.command_executor import get_first_github_token
        return bool(get_first_github_token())
    return bool(get_provider_api_key(provider_name))


def set_provider_runtime_key(provider_name: str, value: Optional[str]) -> None:
    """Update the live in-process credential view for a provider."""
    normalized_value = value.strip() if isinstance(value, str) else None
    if normalized_value == "":
        normalized_value = None

    for env_var in get_provider_env_vars(provider_name):
        if normalized_value is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = normalized_value

    for attr in get_provider_setting_attrs(provider_name):
        setattr(settings, attr, normalized_value)
