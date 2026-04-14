"""GitHub Copilot Chat API client.

GitHub Copilot exposes an OpenAI-compatible chat/completions endpoint at
https://api.githubcopilot.com. The current backend accepts the user's
GitHub OAuth/PAT token directly as a Bearer token, along with the editor
headers Copilot expects.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

COPILOT_API_BASE = "https://api.githubcopilot.com"

# Header constants that the Copilot backend expects (matches VS Code client)
_COPILOT_HEADERS = {
    "Editor-Version": "vscode/1.95.0",
    "Editor-Plugin-Version": "copilot-chat/0.22.0",
    "User-Agent": "GithubCopilot/1.232.0",
    "Copilot-Integration-Id": "vscode-chat",
}


# In-memory cache: github_token_prefix → (is_valid, cache_until_ts)
_TOKEN_CACHE: dict[str, Tuple[bool, float]] = {}


async def exchange_for_copilot_token(github_token: str) -> Optional[str]:
    """Return a GitHub token that is usable against the Copilot API.

    The older token-exchange endpoint is no longer reliable. Copilot now
    accepts the GitHub token directly, so callers can treat the validated
    GitHub token as the API key for api.githubcopilot.com.
    """
    if not github_token:
        return None
    return github_token.strip() or None


async def verify_copilot_access(github_token: str) -> Tuple[bool, Optional[str]]:
    """Run a minimal live Copilot probe with the stored GitHub token."""
    if not github_token:
        return False, "No GitHub token is configured"

    key = github_token[:16]
    cached = _TOKEN_CACHE.get(key)
    if cached and time.time() < cached[1]:
        return cached[0], None if cached[0] else "Cached probe failed"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{COPILOT_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Content-Type": "application/json",
                    **_COPILOT_HEADERS,
                },
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                    "stream": False,
                },
            )
            ok = response.status_code == 200
            _TOKEN_CACHE[key] = (ok, time.time() + 300)
            if ok:
                return True, None
            error_text = response.text[:200] if response.text else f"HTTP {response.status_code}"
            logger.warning("Copilot live probe failed: %s %s", response.status_code, error_text)
            return False, error_text
    except Exception as exc:
        logger.warning("Copilot live probe exception: %s", exc)
        return False, f"{type(exc).__name__}: {exc}"


async def list_copilot_models(github_token: str) -> list[str]:
    """Return the live GitHub Copilot model IDs available to this token."""
    token = (github_token or "").strip()
    if not token:
        return []

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{COPILOT_API_BASE}/models",
            headers={
                "Authorization": f"Bearer {token}",
                **_COPILOT_HEADERS,
            },
        )
        response.raise_for_status()
        payload = response.json()

    return [
        (item.get("id") or "").strip()
        for item in payload.get("data", [])
        if (item.get("id") or "").strip()
    ]


def get_copilot_headers() -> dict:
    """Extra headers Copilot expects on chat/completions requests."""
    return dict(_COPILOT_HEADERS)
