"""Generic OAuth routes that work with any configured provider.

Complements the existing provider-specific routes (e.g. github_oauth.py)
with a unified interface:

  GET  /v1/auth/providers              → list configured providers
  GET  /v1/auth/{provider}             → redirect to provider's authorize URL
  GET  /v1/auth/{provider}/callback    → handle OAuth callback (code exchange)

Adding a new provider requires only:
  1. Create a subclass of BaseOAuthProvider in services/oauth_providers.py
  2. Add env vars ({PROVIDER}_CLIENT_ID / _CLIENT_SECRET)
  3. Register it in build_provider_registry()
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.config import settings
from app.services.oauth_providers import get_provider_registry, OAuthUserProfile
from app.services.oauth_secrets import upsert_user_oauth_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["oauth"])

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_USERS_FILE = _DATA_DIR / "collab_users.json"


# ─── Persistence (mirrors github_oauth.py / collaboration.py helpers) ────────

def _load_users() -> dict:
    """Load users dict from disk."""
    if _USERS_FILE.exists():
        try:
            return json.loads(_USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_users(users: dict):
    """Persist users dict to disk."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/providers")
async def list_providers():
    """List all configured OAuth providers.

    Returns only providers whose client_id and client_secret are set.
    """
    registry = get_provider_registry()
    return {
        "providers": [
            {
                "name": prov.name,
                "display_name": prov.display_name,
                "login_url": f"/v1/auth/{prov.name}",
            }
            for prov in registry.values()
        ]
    }


@router.get("/{provider}")
async def oauth_login(provider: str):
    """Redirect the user to the OAuth provider's authorization page.

    The frontend can either open this URL in a popup or navigate to it
    directly.
    """
    registry = get_provider_registry()
    prov = registry.get(provider)
    if not prov:
        raise HTTPException(
            status_code=404,
            detail=(
                f"OAuth provider '{provider}' not configured. "
                f"Available: {list(registry.keys())}"
            ),
        )

    import secrets
    state = secrets.token_urlsafe(32)
    url = prov.get_auth_url(state=state)
    return RedirectResponse(url=url)


@router.get("/{provider}/callback")
async def oauth_callback(provider: str, code: str, state: str = ""):
    """Handle OAuth callback — exchange code, fetch profile, issue JWT.

    Works identically to the provider-specific github_oauth.py flow but
    uses the generic BaseOAuthProvider interface.
    """
    registry = get_provider_registry()
    prov = registry.get(provider)
    if not prov:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    # Exchange code → access token → user profile
    try:
        token = await prov.exchange_code(code)
        profile: OAuthUserProfile = await prov.get_user_profile(token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("OAuth error for provider %s", provider)
        raise HTTPException(status_code=502, detail=f"OAuth error: {exc}")

    # Find-or-create local user (dict keyed by user_id, same format as
    # github_oauth.py and collaboration.py)
    users = _load_users()
    now = _now_iso()

    # Match by provider-specific ID first, then by username
    user = None
    for u in users.values():
        if u.get(f"{provider}_id") == profile.provider_user_id:
            user = u
            break
    if not user:
        for u in users.values():
            if u.get("username") == profile.username:
                user = u
                break

    if user:
        # Update existing user with latest provider data
        user[f"{provider}_id"] = profile.provider_user_id
        user[f"{provider}_login"] = profile.username
        user[f"{provider}_token"] = profile.access_token
        user["avatar_url"] = profile.avatar_url or user.get("avatar_url")
        user["last_active"] = now
        if profile.email and not user.get("email"):
            user["email"] = profile.email
    else:
        # Create new user — first user gets "owner" role
        role = "owner" if not users else "member"
        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "username": profile.username or f"{provider}-{profile.provider_user_id}",
            "display_name": profile.display_name,
            "email": profile.email,
            "role": role,
            "is_active": True,
            "password_hash": "",  # OAuth-only users have no password
            "auth_provider": provider,
            f"{provider}_id": profile.provider_user_id,
            f"{provider}_login": profile.username,
            f"{provider}_token": profile.access_token,
            "avatar_url": profile.avatar_url,
            "created_at": now,
            "last_active": now,
        }
        users[user_id] = user

    _save_users(users)

    # Persist OAuth token in encrypted DB store (incremental migration path).
    try:
        await upsert_user_oauth_token(
            user_id=str(user.get("id") or ""),
            provider=provider,
            token=profile.access_token or "",
        )
    except Exception as exc:
        logger.warning("Could not persist encrypted OAuth token for %s: %s", provider, exc)

    # Issue JWT (identical to github_oauth.py flow)
    from app.routes.collaboration import _create_jwt

    jwt_token = _create_jwt(user)
    safe_user = {
        k: v for k, v in user.items()
        if k not in ("password_hash", f"{provider}_token")
    }

    return {
        "token": jwt_token,
        "expires_in_seconds": settings.jwt_expiry_hours * 3600,
        "user": safe_user,
    }
