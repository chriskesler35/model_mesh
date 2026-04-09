"""Role-Based Access Control middleware for DevForgeAI."""

from fastapi import Depends, HTTPException, Request

ROLE_HIERARCHY = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}


def require_role(*roles):
    """Return a FastAPI dependency that enforces minimum role level.

    Uses hierarchy: owner > admin > member > viewer.
    If the user's role is >= the minimum required role, access is granted.
    """
    min_level = min(ROLE_HIERARCHY.get(r, 0) for r in roles)

    async def _check(request: Request):
        user = getattr(request.state, "user", None)
        user_role = "viewer"
        if isinstance(user, dict):
            user_role = user.get("role", "viewer")
        elif user:
            user_role = getattr(user, "role", "viewer") or "viewer"
        user_level = ROLE_HIERARCHY.get(user_role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions: requires {'/'.join(roles)}",
            )

    return Depends(_check)
