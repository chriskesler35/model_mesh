"""Context snapshot and session recovery endpoints."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.middleware.auth import verify_api_key
from app.services.context_snapshot import (
    read_snapshot, list_recent_snapshots, read_memory, update_memory
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/context",
    tags=["context"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/recover/{conversation_id}")
async def recover_session(conversation_id: str, db: AsyncSession = Depends(get_db)):
    """
    Find the latest snapshot for a conversation and return it for recovery.
    Also returns the full message history from the DB if available.
    """
    snapshot = read_snapshot(conversation_id)

    # Also pull messages from DB for full fidelity recovery
    db_messages = []
    try:
        from app.models import Message, Conversation
        import uuid
        conv = await db.get(Conversation, uuid.UUID(conversation_id))
        if conv:
            result = await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
            msgs = result.scalars().all()
            db_messages = [
                {
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in msgs
            ]
    except Exception as e:
        logger.warning(f"Could not load DB messages for recovery: {e}")

    if not snapshot and not db_messages:
        raise HTTPException(status_code=404, detail="No snapshot or messages found for this conversation")

    return {
        "conversation_id": conversation_id,
        "snapshot": snapshot,
        "db_messages": db_messages,
        "message_count": len(db_messages),
        "recovery_summary": snapshot.get("raw", "")[:500] if snapshot else None,
    }


@router.get("/snapshots")
async def list_snapshots(days: int = 7):
    """List all session snapshots from the last N days."""
    return {
        "snapshots": list_recent_snapshots(days),
        "days": days,
    }


@router.get("/memory")
async def get_memory():
    """Read the long-term MEMORY.md file."""
    content = read_memory()
    return {
        "content": content,
        "exists": bool(content),
        "char_count": len(content),
    }


@router.put("/memory")
async def save_memory(body: dict):
    """Manually append a note to MEMORY.md."""
    note = body.get("note", "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="note is required")
    update_memory(note, source="manual")
    return {"status": "ok", "appended_chars": len(note)}
