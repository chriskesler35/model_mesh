"""Host file access tools exposed through FastAPI."""

from __future__ import annotations

import os

import aiofiles
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth import verify_api_key


router = APIRouter(
    prefix="/v1/tools",
    tags=["tools"],
    dependencies=[Depends(verify_api_key)],
)

_MAX_FILE_CHARS = 600_000


class FileRequest(BaseModel):
    filepath: str


class WriteFileRequest(BaseModel):
    filepath: str
    content: str


@router.post("/read_file")
async def read_local_file(request: FileRequest) -> dict:
    """Tool endpoint for reading local configuration files by absolute path."""
    target_path = os.path.abspath(os.path.expanduser(request.filepath or ""))
    if not target_path:
        raise HTTPException(status_code=400, detail="filepath is required")

    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail=f"File not found: {target_path}")
    if not os.path.isfile(target_path):
        raise HTTPException(status_code=400, detail=f"Path is not a file: {target_path}")

    try:
        async with aiofiles.open(target_path, mode="r", encoding="utf-8", errors="replace") as f:
            content = await f.read(_MAX_FILE_CHARS + 1)
        truncated = len(content) > _MAX_FILE_CHARS
        if truncated:
            content = content[:_MAX_FILE_CHARS] + "\n\n[…file truncated…]"
        return {
            "status": "success",
            "filepath": target_path,
            "content": content,
            "truncated": truncated,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/write_file")
async def write_local_file(request: WriteFileRequest) -> dict:
    """Tool endpoint for writing local files by absolute path."""
    target_path = os.path.abspath(os.path.expanduser(request.filepath or ""))
    if not target_path:
        raise HTTPException(status_code=400, detail="filepath is required")

    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        async with aiofiles.open(target_path, mode="w", encoding="utf-8") as f:
            await f.write(request.content or "")
        return {
            "status": "success",
            "filepath": target_path,
            "message": "File written successfully.",
            "bytes_written": len((request.content or "").encode("utf-8")),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
