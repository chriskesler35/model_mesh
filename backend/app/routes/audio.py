"""Audio transcription routes — speech-to-text via OpenAI Whisper."""

import os
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from app.middleware.auth import verify_api_key
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/audio", tags=["audio"])


@router.post("/transcribe")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key),
):
    """Transcribe audio file using OpenAI Whisper API.

    Accepts audio in webm, mp3, wav, or ogg format (max 25MB).
    Returns the transcribed text.
    """
    # Validate file type
    allowed_types = {
        "audio/webm", "audio/mpeg", "audio/wav", "audio/mp3",
        "audio/ogg", "video/webm",
    }
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            422,
            f"Unsupported audio format: {file.content_type}. "
            "Supported: webm, mp3, wav, ogg",
        )

    audio_data = await file.read()
    if len(audio_data) > 25 * 1024 * 1024:  # 25MB — Whisper max
        raise HTTPException(413, "Audio file too large. Maximum 25MB.")

    if len(audio_data) == 0:
        raise HTTPException(422, "Empty audio file.")

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        raise HTTPException(
            503, "OpenAI API key not configured for transcription"
        )

    # Call OpenAI Whisper API
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {openai_key}"},
                files={
                    "file": (
                        file.filename or "audio.webm",
                        audio_data,
                        file.content_type or "audio/webm",
                    )
                },
                data={
                    "model": "whisper-1",
                    "response_format": "json",
                },
            )
    except httpx.TimeoutException:
        logger.error("Whisper API request timed out")
        raise HTTPException(504, "Transcription request timed out")
    except httpx.RequestError as exc:
        logger.error("Whisper API request failed: %s", exc)
        raise HTTPException(502, f"Transcription request failed: {exc}")

    if resp.status_code != 200:
        logger.warning(
            "Whisper API returned %d: %s", resp.status_code, resp.text[:500]
        )
        raise HTTPException(502, f"Transcription failed: {resp.text}")

    result = resp.json()
    return {
        "text": result.get("text", ""),
        "duration_seconds": result.get("duration"),
    }
