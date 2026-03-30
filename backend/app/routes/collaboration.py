"""Collaboration & Multi-User — shared workspaces, audit log, session handoff."""

import uuid
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/collab", tags=["collaboration"], dependencies=[Depends(verify_api_key)])

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_USERS_FILE = _DATA_DIR / "collab_users.json"
_AUDIT_FILE = _DATA_DIR / "audit_log.json"
_SESSIONS_FILE = _DATA_DIR / "collab_sessions.json"


# ─── Persistence ──────────────────────────────────────────────────────────────
def _load(path: Path) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {} if path.suffix == ".json" else []


def _save(path: Path, data: Any):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ─── Models ───────────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    username: str
    display_name: str
    password: str
    role: str = "member"  # owner | admin | member | viewer


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class AuditEntry(BaseModel):
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[str] = None
    user: str = "system"


class SessionHandoff(BaseModel):
    from_user: str
    to_user: str
    conversation_id: str
    note: Optional[str] = None


class SharedWorkspace(BaseModel):
    name: str
    description: Optional[str] = None
    project_ids: List[str] = []
    member_ids: List[str] = []


# ─── Users ────────────────────────────────────────────────────────────────────
@router.get("/users")
async def list_users():
    users = _load(_USERS_FILE)
    safe = []
    for u in users.values():
        safe.append({k: v for k, v in u.items() if k != "password_hash"})
    return {"data": safe, "total": len(safe)}


@router.post("/users")
async def create_user(body: UserCreate):
    users = _load(_USERS_FILE)
    if any(u["username"] == body.username for u in users.values()):
        raise HTTPException(status_code=409, detail="Username already exists")
    user_id = str(uuid.uuid4())
    users[user_id] = {
        "id": user_id, "username": body.username,
        "display_name": body.display_name, "role": body.role,
        "password_hash": _hash_password(body.password),
        "is_active": True, "created_at": _now(), "last_active": None,
    }
    _save(_USERS_FILE, users)
    _audit("user_created", "user", user_id, f"User {body.username} created with role {body.role}")
    return {k: v for k, v in users[user_id].items() if k != "password_hash"}


@router.patch("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdate):
    users = _load(_USERS_FILE)
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    if body.display_name is not None: users[user_id]["display_name"] = body.display_name
    if body.role is not None: users[user_id]["role"] = body.role
    if body.is_active is not None: users[user_id]["is_active"] = body.is_active
    _save(_USERS_FILE, users)
    return {k: v for k, v in users[user_id].items() if k != "password_hash"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    users = _load(_USERS_FILE)
    if user_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    username = users[user_id]["username"]
    del users[user_id]
    _save(_USERS_FILE, users)
    _audit("user_deleted", "user", user_id, f"User {username} deleted")
    return {"ok": True}


# ─── Audit log ────────────────────────────────────────────────────────────────
def _audit(action: str, resource_type: str, resource_id: Optional[str] = None,
           details: Optional[str] = None, user: str = "system"):
    log = _load(_AUDIT_FILE) if _AUDIT_FILE.exists() else []
    if not isinstance(log, list):
        log = []
    log.append({
        "id": str(uuid.uuid4()), "ts": _now(),
        "action": action, "resource_type": resource_type,
        "resource_id": resource_id, "details": details, "user": user,
    })
    # Keep last 1000 entries
    if len(log) > 1000:
        log = log[-1000:]
    _save(_AUDIT_FILE, log)


@router.post("/audit")
async def log_audit(body: AuditEntry):
    _audit(body.action, body.resource_type, body.resource_id, body.details, body.user)
    return {"ok": True}


@router.get("/audit")
async def get_audit_log(limit: int = 50, resource_type: Optional[str] = None, user: Optional[str] = None):
    log = _load(_AUDIT_FILE) if _AUDIT_FILE.exists() else []
    if not isinstance(log, list):
        log = []
    if resource_type:
        log = [e for e in log if e.get("resource_type") == resource_type]
    if user:
        log = [e for e in log if e.get("user") == user]
    log = list(reversed(log))[:limit]
    return {"data": log, "total": len(log)}


# ─── Session handoff ──────────────────────────────────────────────────────────
@router.post("/handoff")
async def handoff_session(body: SessionHandoff):
    """Hand off a conversation from one user to another."""
    sessions = _load(_SESSIONS_FILE)
    handoff_id = str(uuid.uuid4())
    sessions[handoff_id] = {
        "id": handoff_id, "from_user": body.from_user, "to_user": body.to_user,
        "conversation_id": body.conversation_id, "note": body.note,
        "status": "pending", "created_at": _now(), "accepted_at": None,
    }
    _save(_SESSIONS_FILE, sessions)
    _audit("session_handoff", "conversation", body.conversation_id,
           f"Handoff from {body.from_user} to {body.to_user}: {body.note or ''}")
    return sessions[handoff_id]


@router.get("/handoff")
async def list_handoffs(user: Optional[str] = None, status: Optional[str] = None):
    sessions = _load(_SESSIONS_FILE)
    data = list(sessions.values())
    if user:
        data = [s for s in data if s.get("to_user") == user or s.get("from_user") == user]
    if status:
        data = [s for s in data if s.get("status") == status]
    return {"data": sorted(data, key=lambda x: x["created_at"], reverse=True)}


@router.post("/handoff/{handoff_id}/accept")
async def accept_handoff(handoff_id: str):
    sessions = _load(_SESSIONS_FILE)
    if handoff_id not in sessions:
        raise HTTPException(status_code=404, detail="Handoff not found")
    sessions[handoff_id]["status"] = "accepted"
    sessions[handoff_id]["accepted_at"] = _now()
    _save(_SESSIONS_FILE, sessions)
    return sessions[handoff_id]


# ─── Shared workspaces ────────────────────────────────────────────────────────
_WORKSPACES_FILE = _DATA_DIR / "workspaces.json"


@router.get("/workspaces")
async def list_workspaces():
    ws = _load(_WORKSPACES_FILE)
    return {"data": list(ws.values()), "total": len(ws)}


@router.post("/workspaces")
async def create_workspace(body: SharedWorkspace):
    ws = _load(_WORKSPACES_FILE)
    ws_id = str(uuid.uuid4())
    ws[ws_id] = {
        "id": ws_id, "name": body.name, "description": body.description,
        "project_ids": body.project_ids, "member_ids": body.member_ids,
        "created_at": _now(), "updated_at": _now(),
    }
    _save(_WORKSPACES_FILE, ws)
    _audit("workspace_created", "workspace", ws_id, f"Workspace '{body.name}' created")
    return ws[ws_id]


@router.patch("/workspaces/{ws_id}")
async def update_workspace(ws_id: str, body: SharedWorkspace):
    ws = _load(_WORKSPACES_FILE)
    if ws_id not in ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws[ws_id].update({
        "name": body.name, "description": body.description,
        "project_ids": body.project_ids, "member_ids": body.member_ids,
        "updated_at": _now(),
    })
    _save(_WORKSPACES_FILE, ws)
    return ws[ws_id]


@router.delete("/workspaces/{ws_id}")
async def delete_workspace(ws_id: str):
    ws = _load(_WORKSPACES_FILE)
    if ws_id not in ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    del ws[ws_id]
    _save(_WORKSPACES_FILE, ws)
    return {"ok": True}
