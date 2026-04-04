"""Share links — generate one-off public links to specific conversations/projects.

Like Google Docs "anyone with the link" sharing. The share token is a random
URL-safe string that grants view-only (or edit) access to a single resource
without requiring login.
"""

import uuid
import json
import secrets
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Literal
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from app.middleware.auth import verify_api_key
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Authenticated router — creating/listing/deleting shares requires the user to be logged in
router = APIRouter(prefix="/v1/shares", tags=["shares"], dependencies=[Depends(verify_api_key)])

# Public router — using a share token requires NO auth (that's the whole point)
public_router = APIRouter(prefix="/v1/share", tags=["shares"])

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_SHARES_FILE = _DATA_DIR / "share_tokens.json"


# ─── Persistence ──────────────────────────────────────────────────────────────
def _load_shares() -> dict:
    if _SHARES_FILE.exists():
        try:
            return json.loads(_SHARES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_shares(data: dict):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SHARES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_expired(share: dict) -> bool:
    expires = share.get("expires_at")
    if not expires:
        return False
    try:
        return datetime.now(timezone.utc) > datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except Exception:
        return False


# ─── Schemas ──────────────────────────────────────────────────────────────────
ResourceType = Literal["conversation", "project", "workspace"]
AccessLevel = Literal["view", "comment", "edit"]


class CreateShareRequest(BaseModel):
    resource_type: ResourceType
    resource_id: str
    access_level: AccessLevel = "view"
    expires_in_days: Optional[int] = 7  # None = never expires


class ShareResponse(BaseModel):
    id: str
    token: str
    url: str  # full shareable URL
    resource_type: str
    resource_id: str
    access_level: str
    created_at: str
    expires_at: Optional[str]
    created_by: str


# ─── Authenticated endpoints (manage shares) ──────────────────────────────────
@router.post("", response_model=ShareResponse)
async def create_share(body: CreateShareRequest, request: Request):
    """Create a new share token for a resource.

    Returns the shareable URL; the caller (frontend) uses this to render a
    "copy link" button.
    """
    user = getattr(request.state, "user", {"id": "owner", "username": "owner"})
    shares = _load_shares()

    share_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(24)  # ~32 chars, URL-safe
    expires_at = None
    if body.expires_in_days is not None and body.expires_in_days > 0:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)).isoformat()

    shares[share_id] = {
        "id": share_id,
        "token": token,
        "resource_type": body.resource_type,
        "resource_id": body.resource_id,
        "access_level": body.access_level,
        "created_at": _now(),
        "expires_at": expires_at,
        "created_by": user.get("username", "owner"),
        "view_count": 0,
    }
    _save_shares(shares)

    # Build the full URL — caller may also want just the token.
    # Frontend will resolve this relative to its own host.
    base_url = str(request.base_url).rstrip("/")
    # Strip the backend port; share URLs point at the FRONTEND, not backend.
    # We don't know the frontend URL from the backend, so just return the path.
    share_url = f"/share/{token}"

    logger.info(f"Share created by {user.get('username')}: {body.resource_type}/{body.resource_id} → {token[:8]}…")
    return ShareResponse(
        id=share_id,
        token=token,
        url=share_url,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        access_level=body.access_level,
        created_at=shares[share_id]["created_at"],
        expires_at=expires_at,
        created_by=user.get("username", "owner"),
    )


@router.get("")
async def list_shares(request: Request, resource_id: Optional[str] = None):
    """List shares created by the current user (or all shares if owner/admin)."""
    user = getattr(request.state, "user", {"role": "owner", "username": "owner"})
    shares = _load_shares()

    results = []
    for s in shares.values():
        if resource_id and s.get("resource_id") != resource_id:
            continue
        # Non-admins only see their own
        if user.get("role") not in ("owner", "admin") and s.get("created_by") != user.get("username"):
            continue
        results.append({
            **s,
            "expired": _is_expired(s),
        })
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"data": results, "total": len(results)}


@router.delete("/{share_id}")
async def revoke_share(share_id: str, request: Request):
    """Revoke a share link (immediately invalidates the token)."""
    user = getattr(request.state, "user", {"role": "owner", "username": "owner"})
    shares = _load_shares()
    if share_id not in shares:
        raise HTTPException(status_code=404, detail="Share not found")
    # Only owner/admin OR the creator can revoke
    creator = shares[share_id].get("created_by")
    if user.get("role") not in ("owner", "admin") and creator != user.get("username"):
        raise HTTPException(status_code=403, detail="You can only revoke your own shares")
    del shares[share_id]
    _save_shares(shares)
    return {"ok": True}


# ─── Public endpoints (consume shares without auth) ───────────────────────────
async def _resolve_share_token(token: str) -> dict:
    """Find and validate a share token. Raises 404 if invalid/expired."""
    shares = _load_shares()
    for s in shares.values():
        if s.get("token") == token:
            if _is_expired(s):
                raise HTTPException(status_code=410, detail="Share link has expired")
            # Increment view count (best-effort)
            s["view_count"] = s.get("view_count", 0) + 1
            s["last_viewed_at"] = _now()
            _save_shares(shares)
            return s
    raise HTTPException(status_code=404, detail="Share link not found")


@public_router.get("/{token}")
async def resolve_share(token: str, db: AsyncSession = Depends(get_db)):
    """Public endpoint — resolve a share token to its resource.

    Returns the resource data (conversation, project, or workspace) in
    read-only format. No authentication required — possession of the
    token IS the authorization.
    """
    share = await _resolve_share_token(token)
    resource_type = share["resource_type"]
    resource_id = share["resource_id"]
    access = share["access_level"]

    # Load the referenced resource based on type
    if resource_type == "conversation":
        from app.models import Conversation, Message
        from sqlalchemy import select
        try:
            conv_uuid = uuid.UUID(resource_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Invalid resource ID")
        conv = await db.get(Conversation, conv_uuid)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation no longer exists")
        msgs_result = await db.execute(
            select(Message).where(Message.conversation_id == conv_uuid).order_by(Message.created_at.asc())
        )
        messages = msgs_result.scalars().all()
        return {
            "share": {
                "token": token,
                "access_level": access,
                "expires_at": share.get("expires_at"),
                "created_by": share.get("created_by"),
            },
            "resource_type": "conversation",
            "data": {
                "id": str(conv.id),
                "title": conv.title,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "messages": [
                    {
                        "id": str(m.id),
                        "role": m.role,
                        "content": m.content,
                        "image_url": m.image_url,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in messages
                ],
            },
        }

    elif resource_type == "project":
        # Projects are stored in data/projects.json (file-backed)
        from app.routes.projects import _load_projects
        projects = _load_projects()
        project = projects.get(resource_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project no longer exists")
        return {
            "share": {
                "token": token,
                "access_level": access,
                "expires_at": share.get("expires_at"),
                "created_by": share.get("created_by"),
            },
            "resource_type": "project",
            "data": project,
        }

    elif resource_type == "workspace":
        workspaces_file = _DATA_DIR / "workspaces.json"
        workspaces = {}
        if workspaces_file.exists():
            try:
                workspaces = json.loads(workspaces_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        ws = workspaces.get(resource_id)
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace no longer exists")
        return {
            "share": {
                "token": token,
                "access_level": access,
                "expires_at": share.get("expires_at"),
                "created_by": share.get("created_by"),
            },
            "resource_type": "workspace",
            "data": ws,
        }

    raise HTTPException(status_code=400, detail=f"Unknown resource type: {resource_type}")
