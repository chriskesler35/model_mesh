"""GitHub Copilot Chat API client.

GitHub Copilot exposes an OpenAI-compatible chat/completions endpoint at
https://api.githubcopilot.com. The current backend accepts the user's
GitHub OAuth/PAT token directly as a Bearer token, along with the editor
headers Copilot expects.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
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

# Copilot session token cache: github_token_prefix → (session_token, expires_ts)
# Session tokens expire in ~30 minutes; we refresh 60 s early.
_SESSION_TOKEN_CACHE: dict[str, Tuple[str, float]] = {}

# DB-backed token cache: populated once at startup via init_db_token_cache().
# Keys are provider names (e.g. "github"); values are decrypted tokens.
_DB_TOKEN_CACHE: dict[str, str] = {}


def _load_first_collaboration_github_token() -> Optional[str]:
    """Return first github token from DB cache, falling back to JSON file."""
    # DB cache is populated at startup by init_db_token_cache(); prefer it.
    cached = _DB_TOKEN_CACHE.get("github", "").strip()
    if cached:
        return cached

    users_file = Path(__file__).parent.parent.parent.parent / "data" / "collab_users.json"
    if not users_file.exists():
        return None
    try:
        users = json.loads(users_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    iterable = users.values() if isinstance(users, dict) else users if isinstance(users, list) else []
    for user in iterable:
        if not isinstance(user, dict):
            continue
        token = (user.get("github_token") or "").strip()
        if token:
            return token
    return None


async def init_db_token_cache() -> None:
    """Populate _DB_TOKEN_CACHE from the oauth_credentials table.

    Called once during application startup so synchronous callers can read
    DB-backed tokens without needing an async DB session.
    """
    try:
        from app.services.oauth_secrets import get_any_provider_token_from_db
        github_token = await get_any_provider_token_from_db("github")
        if github_token:
            _DB_TOKEN_CACHE["github"] = github_token
            logger.info("DB token cache populated: github token loaded from DB")
    except Exception as exc:
        logger.warning("init_db_token_cache failed (non-fatal): %s", exc)


def get_copilot_auth_token_with_source() -> tuple[Optional[str], str]:
    """Return the best-available token and where it came from.

    Priority:
      1) GITHUB_COPILOT_TOKEN (explicitly intended for Copilot API)
      2) DB-backed token cache (populated from oauth_credentials at startup)
         or collaboration JSON file fallback
      3) GITHUB_TOKEN fallback (often PAT; may be rejected by Copilot API)
    """
    explicit = (os.environ.get("GITHUB_COPILOT_TOKEN") or "").strip()
    if explicit:
        return explicit, "env_github_copilot_token"

    collab = _load_first_collaboration_github_token()
    if collab:
        source = "db_oauth_credential" if _DB_TOKEN_CACHE.get("github") else "collaboration_user"
        return collab, source

    generic = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if generic:
        return generic, "env_github_token"

    return None, "none"


def get_copilot_auth_token() -> Optional[str]:
    token, _ = get_copilot_auth_token_with_source()
    return token


def is_pat_rejection_error_text(text: Optional[str]) -> bool:
    normalized = (text or "").lower()
    return "personal access tokens are not supported" in normalized


async def exchange_for_copilot_token(github_token: str) -> Optional[str]:
    """Exchange a GitHub OAuth token for a short-lived Copilot session token.

    GitHub's Copilot API returns the full model catalog (including Claude,
    Gemini, o3, etc.) only when called with a proper Copilot session token
    obtained from /copilot_internal/v2/token.  This endpoint requires the
    OAuth token to have the ``copilot`` scope.

    Falls back to returning the original github_token if the exchange fails
    (e.g. token lacks ``copilot`` scope — only basic GPT models will be
    available in that case).
    """
    if not github_token:
        return None

    token = github_token.strip()
    cache_key = token[:16]
    cached = _SESSION_TOKEN_CACHE.get(cache_key)
    if cached and time.time() < cached[1]:
        return cached[0]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.github.com/copilot_internal/v2/token",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/json",
                },
            )
        if resp.status_code == 200:
            data = resp.json()
            session_token = (data.get("token") or "").strip()
            if session_token:
                # Parse expiry; tokens usually live ~30 min. Refresh 60 s early.
                expires_at_str = data.get("expires_at") or ""
                try:
                    from datetime import datetime, timezone
                    expires_ts = datetime.fromisoformat(
                        expires_at_str.replace("Z", "+00:00")
                    ).timestamp() - 60.0
                except Exception:
                    expires_ts = time.time() + 1740.0  # 29 min fallback
                _SESSION_TOKEN_CACHE[cache_key] = (session_token, expires_ts)
                logger.debug("Copilot session token exchanged, expires ~%s", expires_at_str)
                return session_token
        elif resp.status_code == 404:
            logger.info(
                "Copilot token exchange returned 404 — token likely lacks 'copilot' scope. "
                "Re-connect GitHub to get the full model catalog."
            )
        else:
            logger.warning("Copilot token exchange failed: %s %s", resp.status_code, resp.text[:120])
    except Exception as exc:
        logger.warning("Copilot token exchange exception: %s", exc)

    # Fallback: use the raw OAuth token (only basic GPT models available)
    return token


async def verify_copilot_access(github_token: str) -> Tuple[bool, Optional[str]]:
    """Run a minimal live Copilot probe with the stored GitHub token."""
    if not github_token:
        return False, "No GitHub token is configured"

    key = github_token[:16]
    cached = _TOKEN_CACHE.get(key)
    if cached and time.time() < cached[1]:
        return cached[0], None if cached[0] else "Cached probe failed"

    # Use session token for the probe if available (avoids scope issues)
    probe_token = await exchange_for_copilot_token(github_token)
    if not probe_token:
        probe_token = github_token

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{COPILOT_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {probe_token}",
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

    # Use session token for the full model catalog when copilot scope is available.
    api_token = await exchange_for_copilot_token(token) or token

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{COPILOT_API_BASE}/models",
            headers={
                "Authorization": f"Bearer {api_token}",
                **_COPILOT_HEADERS,
            },
        )
        if response.status_code == 400 and is_pat_rejection_error_text(response.text):
            logger.warning("Copilot model list rejected PAT/third-party token")
            return []
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
