"""Audio endpoints — text-to-speech synthesis and voice listing."""

import os
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/audio",
    tags=["audio"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/synthesize")
async def synthesize_speech(request: Request):
    """Synthesize speech from text using OpenAI TTS API.

    Streams audio back as MP3 so the client can begin playback
    before the full file is ready.
    """
    body = await request.json()
    text = body.get("text", "")
    voice = body.get("voice", "alloy")
    speed = body.get("speed", 1.0)

    if not text:
        raise HTTPException(status_code=422, detail="Text is required")
    if len(text) > 4096:
        raise HTTPException(
            status_code=422,
            detail="Text too long. Maximum 4096 characters.",
        )

    valid_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
    if voice not in valid_voices:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid voice '{voice}'. Choose from: {', '.join(sorted(valid_voices))}",
        )

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured for TTS",
        )

    async def generate():
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1",
                    "input": text,
                    "voice": voice,
                    "speed": speed,
                    "response_format": "mp3",
                },
            ) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    logger.error(
                        "OpenAI TTS error %s: %s",
                        resp.status_code,
                        error_body.decode("utf-8", errors="replace"),
                    )
                    return
                async for chunk in resp.aiter_bytes(1024):
                    yield chunk

    return StreamingResponse(
        generate(),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=speech.mp3"},
    )


@router.get("/voices")
async def list_voices():
    """List available TTS voices."""
    return {
        "voices": [
            {"id": "alloy", "name": "Alloy", "description": "Neutral, balanced"},
            {"id": "echo", "name": "Echo", "description": "Warm, conversational"},
            {"id": "fable", "name": "Fable", "description": "Expressive, storytelling"},
            {"id": "onyx", "name": "Onyx", "description": "Deep, authoritative"},
            {"id": "nova", "name": "Nova", "description": "Bright, energetic"},
            {"id": "shimmer", "name": "Shimmer", "description": "Gentle, soothing"},
        ]
    }
