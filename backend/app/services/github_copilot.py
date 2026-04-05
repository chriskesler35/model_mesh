"""GitHub Copilot Chat API client.

Copilot has an OpenAI-compatible chat/completions endpoint at
https://api.githubcopilot.com, but calls require a short-lived Copilot
token obtained by exchanging a GitHub OAuth/PAT token for one at
https://api.github.com/copilot_internal/v2/token.

Tokens are cached in-memory with their expiry time and refreshed
transparently when LiteLLM calls us.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_API_BASE = "https://api.githubcopilot.com"

# Header constants that the Copilot backend expects (matches VS Code client)
_COPILOT_HEADERS = {
    "Editor-Version": "vscode/1.95.0",
    "Editor-Plugin-Version": "copilot-chat/0.22.0",
    "User-Agent": "GithubCopilot/1.232.0",
    "Copilot-Integration-Id": "vscode-chat",
}


# In-memory cache: github_token_prefix → (copilot_token, expires_at_ts)
_TOKEN_CACHE: dict[str, Tuple[str, float]] = {}


async def exchange_for_copilot_token(github_token: str) -> Optional[str]:
    """Exchange a GitHub PAT/OAuth token for a Copilot session token.

    Returns the Copilot token (starts with "tid=...") or None on failure.
    Caches the result until ~90% of its lifetime has elapsed.
    """
    if not github_token:
        return None
    key = github_token[:16]  # cache by prefix (don't log full token)
    cached = _TOKEN_CACHE.get(key)
    if cached:
        token, expires_at = cached
        if time.time() < expires_at:
            return token

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                COPILOT_TOKEN_URL,
                headers={
                    "Authorization": f"Bearer {github_token}",
                    "Accept": "application/json",
                    **_COPILOT_HEADERS,
                },
            )
            if r.status_code != 200:
                logger.warning(f"Copilot token exchange failed: {r.status_code} {r.text[:200]}")
                return None
            data = r.json()
            token = data.get("token")
            # Copilot returns exp as unix ts; cache until 90% through its lifetime
            exp = data.get("expires_at") or (time.time() + 1500)  # fallback 25min
            lifetime = max(0, exp - time.time())
            cache_until = time.time() + (lifetime * 0.9)
            if token:
                _TOKEN_CACHE[key] = (token, cache_until)
                return token
    except Exception as e:
        logger.warning(f"Copilot token exchange exception: {e}")
    return None


def get_copilot_headers() -> dict:
    """Extra headers Copilot expects on chat/completions requests."""
    return dict(_COPILOT_HEADERS)
