"""Host file access tools exposed through FastAPI."""

from __future__ import annotations

import os
import tempfile
import logging
from uuid import uuid4
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from app.middleware.auth import verify_api_key
from app.services.command_executor import get_media_conversion_status, tool_convert_media


logger = logging.getLogger(__name__)


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


class ConvertMediaRequest(BaseModel):
    source_path: str
    target_format: str
    output_path: Optional[str] = None
    fps: int = 12
    width: Optional[int] = None


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


@router.post("/convert_media")
async def convert_media(request: ConvertMediaRequest) -> dict:
    """Tool endpoint for converting image formats and video files to GIF."""
    workspace_root = Path(__file__).resolve().parents[3]

    result = await tool_convert_media(
        source_path=request.source_path,
        target_format=request.target_format,
        workspace_root=workspace_root,
        output_path=request.output_path,
        fps=request.fps,
        width=request.width,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("output", "Conversion failed"))
    return result


@router.get("/convert_media/status")
async def convert_media_status() -> dict:
    """Return whether backend media conversion dependencies are available."""
    return get_media_conversion_status()


@router.post("/convert_media/upload")
async def convert_media_upload(
    file: UploadFile = File(...),
    target_format: str = Form(...),
    fps: int = Form(12),
    width: Optional[int] = Form(None),
):
    """Upload a media file, convert it, and return the converted file download."""
    workspace_root = Path(__file__).resolve().parents[3]
    upload_dir = Path(tempfile.gettempdir()) / "devforge_media_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "upload.bin").suffix
    source_path = upload_dir / f"{uuid4().hex}{suffix}"
    output_path = upload_dir / f"{uuid4().hex}.{target_format.strip().lower().lstrip('.')}"

    try:
        contents = await file.read()
        source_path.write_bytes(contents)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {exc}") from exc

    try:
        result = await tool_convert_media(
            source_path=str(source_path),
            target_format=target_format,
            workspace_root=workspace_root,
            output_path=str(output_path),
            fps=fps,
            width=width,
        )
    except Exception as exc:
        logger.exception("Unexpected convert_media_upload failure")
        try:
            source_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"Unexpected conversion failure: {exc}") from exc

    if not result.get("success"):
        try:
            source_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=result.get("output", "Conversion failed"))

    if not output_path.exists():
        logger.error(
            "Conversion reported success but output file missing: source=%s target=%s output=%s result=%s",
            source_path,
            target_format,
            output_path,
            result,
        )
        raise HTTPException(
            status_code=400,
            detail="Conversion failed to produce an output file. Check server dependencies (ffmpeg/Pillow) and logs.",
        )

    original_stem = Path(file.filename or "converted").stem or "converted"
    download_name = f"{original_stem}.{target_format.strip().lower().lstrip('.')}"

    def _cleanup_temp_files() -> None:
        try:
            source_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
        except Exception:
            pass

    return FileResponse(
        path=str(output_path),
        filename=download_name,
        media_type="application/octet-stream",
        background=BackgroundTask(_cleanup_temp_files),
    )
