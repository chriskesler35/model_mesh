"""Identity endpoints - serves and saves SOUL.md and USER.md."""

import re
import logging
from pathlib import Path
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/identity", tags=["identity"], dependencies=[Depends(verify_api_key)])

_DATA_DIR = Path(r"G:\Model_Mesh\data")
_SOUL_PATH = _DATA_DIR / "soul.md"
_USER_PATH = _DATA_DIR / "user.md"


class FileContent(BaseModel):
    content: str


def _parse_ai_name(content: str) -> str | None:
    """Extract AI name from soul.md. Looks for '## Name' section or 'name: X' pattern."""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^##\s*name\s*$", line.strip(), re.IGNORECASE):
            # Return next non-empty line
            for j in range(i + 1, len(lines)):
                val = lines[j].strip()
                if val and not val.startswith("#"):
                    return val
        m = re.match(r"^[-*]?\s*\*?\*?name\*?\*?\s*[:\-]\s*(.+)", line.strip(), re.IGNORECASE)
        if m:
            return m.group(1).strip().strip("*")
    return None


@router.get("/status")
async def get_identity_status():
    soul_exists = _SOUL_PATH.exists()
    user_exists = _USER_PATH.exists()
    ai_name = None
    if soul_exists:
        try:
            ai_name = _parse_ai_name(_SOUL_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"soul_exists": soul_exists, "user_exists": user_exists, "ai_name": ai_name or "Aria"}


@router.get("/soul")
async def get_soul():
    if not _SOUL_PATH.exists():
        return {"content": "", "exists": False}
    return {"content": _SOUL_PATH.read_text(encoding="utf-8"), "exists": True}


@router.put("/soul")
async def save_soul(body: FileContent):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SOUL_PATH.write_text(body.content, encoding="utf-8")
    return {"ok": True}


@router.get("/user")
async def get_user():
    if not _USER_PATH.exists():
        return {"content": "", "exists": False}
    return {"content": _USER_PATH.read_text(encoding="utf-8"), "exists": True}


@router.put("/user")
async def save_user(body: FileContent):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _USER_PATH.write_text(body.content, encoding="utf-8")
    return {"ok": True}
