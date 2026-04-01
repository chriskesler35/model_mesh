"""Conversation endpoints."""

from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
import uuid
from app.database import get_db
from app.models import Conversation, Message
from app.schemas import ConversationCreate, ConversationResponse, ConversationList, MessageResponse, MessageList
from app.schemas.conversation import ConversationUpdate
from app.middleware.auth import verify_api_key
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/conversations", tags=["conversations"], dependencies=[Depends(verify_api_key)])


# ─── Message image URL persistence (must be BEFORE /{conversation_id} routes) ─
class MessageImageUpdate(PydanticBaseModel):
    image_url: str


@router.patch("/messages/{message_id}/image")
async def update_message_image(
    message_id: str,
    body: MessageImageUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Save an inline image URL on a message (for persistence across reloads)."""
    try:
        msg_uuid = uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid message ID")
    result = await db.execute(
        select(Message).where(Message.id == msg_uuid)
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.image_url = body.image_url
    await db.commit()
    return {"ok": True}


@router.get("", response_model=ConversationList)
async def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Filter by title"),
    pinned_first: bool = Query(True),
    db: AsyncSession = Depends(get_db)
):
    """List conversations, optionally filtered by title search."""
    query = select(Conversation)

    if search:
        query = query.where(Conversation.title.ilike(f"%{search}%"))

    # Pinned first, then by last_message_at desc, then created_at desc
    if pinned_first:
        query = query.order_by(
            Conversation.pinned.desc(),
            Conversation.last_message_at.desc().nulls_last(),
            Conversation.created_at.desc()
        )
    else:
        query = query.order_by(
            Conversation.last_message_at.desc().nulls_last(),
            Conversation.created_at.desc()
        )

    count_query = select(func.count()).select_from(Conversation)
    if search:
        count_query = count_query.where(Conversation.title.ilike(f"%{search}%"))
    total = await db.scalar(count_query)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    conversations = result.scalars().all()

    return ConversationList(
        data=[ConversationResponse.model_validate(c) for c in conversations],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total
    )


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    conversation: ConversationCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new conversation."""
    data = conversation.model_dump()
    db_conversation = Conversation(**data)
    db.add(db_conversation)
    await db.commit()
    await db.refresh(db_conversation)
    return ConversationResponse.model_validate(db_conversation)


@router.get("/cleanup", include_in_schema=True)
async def cleanup_old_conversations(
    dry_run: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """Delete conversations older than 30 days where keep_forever=False."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    query = select(Conversation).where(
        Conversation.keep_forever == False,
        Conversation.created_at < cutoff
    )
    result = await db.execute(query)
    old_convs = result.scalars().all()

    if dry_run:
        return {"would_delete": len(old_convs), "dry_run": True}

    count = len(old_convs)
    for conv in old_convs:
        await db.delete(conv)
    await db.commit()

    logger.info(f"Cleaned up {count} old conversations (>30 days)")
    return {"deleted": count}


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a single conversation by ID."""
    conv_uuid = uuid.UUID(conversation_id)
    conv = await db.get(Conversation, conv_uuid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationResponse.model_validate(conv)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    updates: ConversationUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update conversation metadata (title, pinned, keep_forever)."""
    conv_uuid = uuid.UUID(conversation_id)
    conv = await db.get(Conversation, conv_uuid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if updates.title is not None:
        conv.title = updates.title[:200]
    if updates.pinned is not None:
        conv.pinned = updates.pinned
    if updates.keep_forever is not None:
        conv.keep_forever = updates.keep_forever

    await db.commit()
    await db.refresh(conv)
    return ConversationResponse.model_validate(conv)


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a conversation and all its messages."""
    conv_uuid = uuid.UUID(conversation_id)
    conv = await db.get(Conversation, conv_uuid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.delete(conv)
    await db.commit()
    return {"status": "deleted", "id": conversation_id}


@router.get("/{conversation_id}/messages", response_model=MessageList)
async def get_messages(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Get messages for a conversation."""
    conv_uuid = uuid.UUID(conversation_id)

    conv = await db.get(Conversation, conv_uuid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    query = select(Message).where(
        Message.conversation_id == conv_uuid
    ).order_by(Message.created_at.asc())

    count_query = select(func.count()).select_from(Message).where(
        Message.conversation_id == conv_uuid
    )
    total = await db.scalar(count_query)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    messages = result.scalars().all()

    return MessageList(
        data=[MessageResponse.model_validate(m) for m in messages],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total
    )


class MessageCreate(PydanticBaseModel):
    role: str
    content: str


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def add_message(
    conversation_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a message to a conversation (for image placeholder, etc.)."""
    conv_uuid = uuid.UUID(conversation_id)

    conv = await db.get(Conversation, conv_uuid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg = Message(
        conversation_id=conv_uuid,
        role=body.role,
        content=body.content,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return MessageResponse.model_validate(msg)



