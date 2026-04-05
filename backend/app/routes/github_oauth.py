"""GitHub OAuth login flow + token storage.

Two flows:
  1. Login: user clicks "Sign in with GitHub" → backend redirects to GitHub's
     authorize URL → GitHub redirects back to frontend /auth/github/callback
     with a code → frontend POSTs code here → we exchange for token, fetch
     user profile, find-or-create a local user, return JWT.
  2. Token reuse: the GitHub token is stored on the user record so later
     git operations (git push) can authenticate without a PAT.
"""

import json
import logging
import secrets
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/auth/github", tags=["github-oauth"])

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_USERS_FILE = _DATA_DIR / "collab_users.json"

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

# Scopes we request:
# - read:user, user:email → profile + verified email for account linking
# - repo → read+write access to user's repos (needed for git push via HTTPS)
DEFAULT_SCOPES = "read:user user:email repo"


def _load_users() -> Dict[str, Any]:
    if _USERS_FILE.exists():
        try:
            return json.loads(_USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_users(users: Dict[str, Any]):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _github_configured() -> bool:
    return bool(settings.github_client_id and settings.github_client_secret)


# ─── Routes ───────────────────────────────────────────────────────────────────
class AuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


@router.get("/status")
async def github_status():
    """Is GitHub OAuth configured + usable?"""
    return {
        "configured": _github_configured(),
        "client_id": settings.github_client_id[:8] + "…" if settings.github_client_id else None,
        "redirect_url": settings.github_oauth_redirect_url,
    }


@router.get("/authorize", response_model=AuthorizeResponse)
async def github_authorize():
    """Return the GitHub authorize URL + a state token.

    Frontend opens this URL in a popup/redirect. GitHub calls back to
    our configured redirect URL with ?code=...&state=...
    """
    if not _github_configured():
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth not configured. Set GITHUB_CLIENT_ID and "
                   "GITHUB_CLIENT_SECRET in .env and restart."
        )
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_oauth_redirect_url,
        "scope": DEFAULT_SCOPES,
        "state": state,
    }
    from urllib.parse import urlencode
    url = f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"
    return AuthorizeResponse(authorize_url=url, state=state)


class CallbackBody(BaseModel):
    code: str
    state: Optional[str] = None


@router.post("/callback")
async def github_callback(body: CallbackBody):
    """Exchange an OAuth code for a GitHub access token + find/create user + JWT."""
    if not _github_configured():
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")

    # 1. Exchange code for access token
    async with httpx.AsyncClient(timeout=20.0) as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": body.code,
                "redirect_uri": settings.github_oauth_redirect_url,
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"GitHub token exchange failed: {token_resp.text[:200]}")
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            err = token_data.get("error_description") or token_data.get("error") or "no access_token"
            raise HTTPException(status_code=400, detail=f"GitHub didn't return a token: {err}")

        # 2. Fetch user profile
        profile_resp = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        if profile_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch GitHub profile")
        profile = profile_resp.json()

        # 3. Fetch verified email (the public email on profile may be null)
        email = profile.get("email")
        if not email:
            emails_resp = await client.get(
                GITHUB_EMAILS_URL,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            if emails_resp.status_code == 200:
                emails = emails_resp.json()
                primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
                if primary:
                    email = primary.get("email")

    github_login = profile.get("login") or ""
    display_name = profile.get("name") or github_login
    avatar_url = profile.get("avatar_url") or ""
    github_id = profile.get("id")

    # 4. Find-or-create the local user
    users = _load_users()
    # Match by github_id first, then by github_login, then create
    user = None
    for u in users.values():
        if u.get("github_id") == github_id:
            user = u
            break
    if not user:
        for u in users.values():
            if u.get("username") == github_login:
                user = u
                break

    now_iso = _now_iso()
    if user:
        # Update existing user with latest GitHub data
        user["github_id"] = github_id
        user["github_login"] = github_login
        user["github_token"] = access_token
        user["avatar_url"] = avatar_url
        user["last_active"] = now_iso
        if email and not user.get("email"):
            user["email"] = email
    else:
        # Create new user — default to 'member' role unless they're the first user
        role = "owner" if not users else "member"
        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "username": github_login or f"github-{github_id}",
            "display_name": display_name,
            "email": email,
            "role": role,
            "is_active": True,
            "password_hash": "",  # GitHub-only users have no password
            "github_id": github_id,
            "github_login": github_login,
            "github_token": access_token,
            "avatar_url": avatar_url,
            "auth_provider": "github",
            "created_at": now_iso,
            "last_active": now_iso,
        }
        users[user_id] = user

    _save_users(users)

    # 5. Issue our JWT so the frontend can use it like password-based login
    from app.routes.collaboration import _create_jwt
    token = _create_jwt(user)

    safe_user = {k: v for k, v in user.items() if k not in ("password_hash", "github_token")}
    return {
        "token": token,
        "expires_in_seconds": settings.jwt_expiry_hours * 3600,
        "user": safe_user,
    }


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ─── Token retrieval helpers (used by git push execution) ────────────────────
def get_user_github_token(user_id: str) -> Optional[str]:
    """Look up a user's stored GitHub access token for git operations."""
    users = _load_users()
    user = users.get(user_id)
    if not user:
        return None
    return user.get("github_token")
