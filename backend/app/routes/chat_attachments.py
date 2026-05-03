"""Chat attachment extraction endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.middleware.auth import verify_api_key
from app.middleware.rate_limit import check_rate_limit
from app.services.document_text_extractor import ExtractionError, extract_document_text


MAX_UPLOAD_BYTES = 25 * 1024 * 1024

router = APIRouter(
    prefix="/v1/chat/attachments",
    tags=["chat-attachments"],
    dependencies=[Depends(verify_api_key), Depends(check_rate_limit)],
)


@router.post("/extract")
async def extract_attachment(
    file: UploadFile = File(...),
    max_chars: int = Form(default=60_000, ge=1_000, le=200_000),
) -> dict:
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
        )

    try:
        payload = extract_document_text(
            filename=file.filename or "attachment",
            content_type=file.content_type,
            raw_bytes=raw_bytes,
            max_chars=max_chars,
        )
        return {"ok": True, **payload}
    except ExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Failed to parse attachment: {exc}") from exc
