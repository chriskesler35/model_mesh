from pathlib import Path
from io import BytesIO

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile
from fastapi.responses import FileResponse

from app.services.command_executor import tool_convert_media
from app.routes import tools as tools_route


@pytest.mark.asyncio
async def test_tool_convert_media_missing_source_returns_error(tmp_path: Path):
    result = await tool_convert_media(
        source_path=str(tmp_path / "does-not-exist.heic"),
        target_format="png",
        workspace_root=tmp_path,
    )

    assert result["success"] is False
    assert "Source file not found" in result["output"]


@pytest.mark.asyncio
async def test_tool_convert_media_video_requires_gif_target(tmp_path: Path):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"fake-video")

    result = await tool_convert_media(
        source_path=str(src),
        target_format="png",
        workspace_root=tmp_path,
    )

    assert result["success"] is False
    assert "target_format='gif' only" in result["output"]


@pytest.mark.asyncio
async def test_convert_media_route_success(monkeypatch):
    async def _fake_convert_media(**kwargs):
        return {
            "success": True,
            "output": "Converted image to .png: C:/tmp/out.png",
            "source_path": kwargs.get("source_path"),
            "output_path": "C:/tmp/out.png",
        }

    monkeypatch.setattr(tools_route, "tool_convert_media", _fake_convert_media)

    req = tools_route.ConvertMediaRequest(
        source_path="C:/tmp/in.heic",
        target_format="png",
        output_path="C:/tmp/out.png",
    )

    result = await tools_route.convert_media(req)

    assert result["success"] is True
    assert result["output_path"] == "C:/tmp/out.png"


@pytest.mark.asyncio
async def test_convert_media_route_failure(monkeypatch):
    async def _fake_convert_media(**kwargs):
        return {
            "success": False,
            "output": "conversion failed",
        }

    monkeypatch.setattr(tools_route, "tool_convert_media", _fake_convert_media)

    req = tools_route.ConvertMediaRequest(
        source_path="C:/tmp/in.heic",
        target_format="png",
    )

    with pytest.raises(HTTPException) as exc:
        await tools_route.convert_media(req)

    assert exc.value.status_code == 400
    assert exc.value.detail == "conversion failed"


@pytest.mark.asyncio
async def test_convert_media_upload_success(monkeypatch, tmp_path: Path):
    async def _fake_convert_media(**kwargs):
        output_file = Path(kwargs["output_path"])
        output_file.write_bytes(b"png-bytes")
        return {
            "success": True,
            "output": "ok",
            "output_path": str(output_file),
        }

    monkeypatch.setattr(tools_route, "tool_convert_media", _fake_convert_media)

    upload = UploadFile(filename="photo.heic", file=BytesIO(b"heic-bytes"))
    response = await tools_route.convert_media_upload(
        file=upload,
        target_format="png",
        fps=12,
        width=None,
    )

    assert isinstance(response, FileResponse)
    assert response.filename == "photo.png"


@pytest.mark.asyncio
async def test_convert_media_upload_failure(monkeypatch):
    async def _fake_convert_media(**kwargs):
        return {
            "success": False,
            "output": "bad input",
        }

    monkeypatch.setattr(tools_route, "tool_convert_media", _fake_convert_media)

    upload = UploadFile(filename="clip.mp4", file=BytesIO(b"video-bytes"))
    with pytest.raises(HTTPException) as exc:
        await tools_route.convert_media_upload(
            file=upload,
            target_format="gif",
            fps=12,
            width=720,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "bad input"
