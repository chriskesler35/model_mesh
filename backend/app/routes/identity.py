"""Identity endpoints — serves and saves SOUL.md, USER.md, and IDENTITY.md."""

import re
import logging
from pathlib import Path
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/identity",
    tags=["identity"],
    dependencies=[Depends(verify_api_key)],
)

# Resolve data dir relative to this file so it works anywhere.
_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"


def _soul_path() -> Path:
    return _DATA_DIR / "soul.md"


def _user_path() -> Path:
    return _DATA_DIR / "user.md"


def _identity_path() -> Path:
    return _DATA_DIR / "identity.md"


class FileContent(BaseModel):
    content: str


def _parse_ai_name(content: str) -> str | None:
    """Extract AI name from soul.md content."""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^##\s*name\s*$", line.strip(), re.IGNORECASE):
            for j in range(i + 1, len(lines)):
                val = lines[j].strip()
                if val and not val.startswith("#"):
                    return val
        m = re.match(r"^[-*]?\s*\*?\*?name\*?\*?\s*[:\-]\s*(.+)", line.strip(), re.IGNORECASE)
        if m:
            return m.group(1).strip().strip("*")
    return None


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_identity_status():
    """Returns setup status for all three identity files."""
    soul_path = _soul_path()
    user_path = _user_path()
    identity_path = _identity_path()

    soul_exists = soul_path.exists() and soul_path.stat().st_size > 10
    user_exists = user_path.exists() and user_path.stat().st_size > 10
    identity_exists = identity_path.exists() and identity_path.stat().st_size > 10

    ai_name = None
    if soul_exists:
        try:
            ai_name = _parse_ai_name(soul_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "soul_exists": soul_exists,
        "user_exists": user_exists,
        "identity_exists": identity_exists,
        # first_run is true if any of the three files is missing/empty
        "first_run": not (soul_exists and user_exists),
        "ai_name": ai_name or "Aria",
    }


# ── SOUL.md ───────────────────────────────────────────────────────────────────

@router.get("/soul")
async def get_soul():
    path = _soul_path()
    if not path.exists():
        return {"content": "", "exists": False}
    return {"content": path.read_text(encoding="utf-8"), "exists": True}


@router.put("/soul")
async def save_soul(body: FileContent):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _soul_path().write_text(body.content, encoding="utf-8")
    return {"ok": True}


# ── USER.md ───────────────────────────────────────────────────────────────────

@router.get("/user")
async def get_user():
    path = _user_path()
    if not path.exists():
        return {"content": "", "exists": False}
    return {"content": path.read_text(encoding="utf-8"), "exists": True}


@router.put("/user")
async def save_user(body: FileContent):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _user_path().write_text(body.content, encoding="utf-8")
    return {"ok": True}


# ── IDENTITY.md ───────────────────────────────────────────────────────────────

@router.get("/identity-file")
async def get_identity_file():
    path = _identity_path()
    if not path.exists():
        return {"content": "", "exists": False}
    return {"content": path.read_text(encoding="utf-8"), "exists": True}


@router.put("/identity-file")
async def save_identity_file(body: FileContent):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _identity_path().write_text(body.content, encoding="utf-8")
    return {"ok": True}


# ── Batch save (used by first-run wizard) ─────────────────────────────────────

class SetupPayload(BaseModel):
    soul: str
    user: str
    identity: str


@router.post("/setup")
async def save_setup(body: SetupPayload):
    """Save all three identity files in a single call (first-run wizard)."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _soul_path().write_text(body.soul, encoding="utf-8")
    _user_path().write_text(body.user, encoding="utf-8")
    _identity_path().write_text(body.identity, encoding="utf-8")
    return {"ok": True}
