"""Authentication middleware — accepts master API key OR per-user JWT tokens."""

import os
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings

security = HTTPBearer()


def _set_owner(request: Request, token: str):
    """Mark request as owner-authenticated via master API key."""
    request.state.api_key = token
    request.state.user = {
        "id": "owner",
        "username": "owner",
        "display_name": "Owner",
        "role": "owner",
        "auth_method": "master_key",
    }


async def verify_api_key(request: Request, credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Verify auth token. Accepts either:

    1. Master MODELMESH_API_KEY → owner-level access (existing behavior)
    2. Per-user JWT token (from POST /v1/auth/login) → user-scoped access

    Attaches the authenticated user to request.state.user.
    """
    token = credentials.credentials

    # 1. Try master API key (owner)
    if token == settings.modelmesh_api_key:
        _set_owner(request, token)
        return token

    # 2. Try JWT token (lazy import to avoid circular deps)
    try:
        from app.routes.collaboration import decode_jwt, get_user_by_id
        payload = decode_jwt(token)
        if payload:
            user = get_user_by_id(payload.get("sub", ""))
            if user and user.get("is_active", True):
                # Valid JWT for an active user
                request.state.api_key = token
                request.state.user = {
                    "id": user["id"],
                    "username": user["username"],
                    "display_name": user.get("display_name", user["username"]),
                    "role": user.get("role", "member"),
                    "auth_method": "jwt",
                }
                return token
    except Exception:
        # Fall through to 401
        pass

    # Neither master key nor valid JWT
    raise HTTPException(
        status_code=401,
        detail={
            "error": {
                "type": "authentication_error",
                "message": "Invalid or expired token",
                "code": "invalid_credentials"
            }
        }
    )


def current_user(request: Request) -> dict:
    """Get the authenticated user from request state (must be called after verify_api_key)."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_role(*roles: str):
    """Dependency factory: require the caller to have one of the given roles.

    Usage: @router.delete("/foo", dependencies=[Depends(require_role("owner", "admin"))])
    """
    async def _check(request: Request):
        user = current_user(request)
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"This action requires one of roles: {', '.join(roles)}"
            )
        return user
    return _check