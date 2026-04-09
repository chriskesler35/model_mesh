"""Conversation endpoints."""

import secrets
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
import uuid
from app.database import get_db
from app.models import Conversation, Message, ConversationShare
from app.schemas import ConversationCreate, ConversationResponse, ConversationList, MessageResponse, MessageList
from app.schemas.conversation import ConversationUpdate, ShareCreate, ShareResponse, SharedConversationResponse, SharedConversationList
from app.middleware.auth import verify_api_key
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/conversations", tags=["conversations"], dependencies=[Depends(verify_api_key)])


def _parse_uuid(value: str) -> uuid.UUID:
    """Parse a string as UUID, raising 404 if invalid."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Not found")


# ─── Message image URL persistence (must be BEFORE /{conversation_id} routes) ─
class MessageImageUpdate(PydanticBaseModel):
    image_url: str
    content: Optional[str] = None  # optionally update message text alongside image URL


@router.patch("/messages/{message_id}/image")
async def update_message_image(
    message_id: str,
    body: MessageImageUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Save an inline image URL (and optional content update) on a message."""
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
    if body.content is not None:
        msg.content = body.content
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

    logger.info(f"Listing conversations: {len(conversations)} returned, {total} total")
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
    logger.info(f"Created conversation {db_conversation.id} title={db_conversation.title!r}")
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
    conv_uuid = _parse_uuid(conversation_id)
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
    conv_uuid = _parse_uuid(conversation_id)
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
    conv_uuid = _parse_uuid(conversation_id)
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
    conv_uuid = _parse_uuid(conversation_id)

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
    conv_uuid = _parse_uuid(conversation_id)

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


# ─── Share endpoints ──────────────────────────────────────────────────────────

@router.get("/shared", response_model=SharedConversationList)
async def list_shared_conversations(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List conversations shared with the current user."""
    current_user_id = request.state.user.get("id", "owner")

    query = (
        select(ConversationShare)
        .where(
            ConversationShare.shared_with_user_id == current_user_id,
            ConversationShare.revoked_at.is_(None),
        )
        .order_by(ConversationShare.created_at.desc())
    )
    result = await db.execute(query)
    shares = result.scalars().all()

    items = []
    for share in shares:
        conv = await db.get(Conversation, share.conversation_id)
        if conv is None:
            continue
        items.append(SharedConversationResponse(
            share_id=share.id,
            conversation_id=share.conversation_id,
            permission=share.permission,
            token=share.token,
            shared_at=share.created_at,
            conversation=ConversationResponse.model_validate(conv),
        ))

    return SharedConversationList(data=items, total=len(items))


@router.post("/{conversation_id}/share", response_model=ShareResponse)
async def create_share(
    conversation_id: str,
    body: ShareCreate,
    db: AsyncSession = Depends(get_db),
):
    """Share a conversation — generates a share token with permissions."""
    conv_uuid = _parse_uuid(conversation_id)
    conv = await db.get(Conversation, conv_uuid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    share = ConversationShare(
        conversation_id=conv_uuid,
        shared_with_user_id=body.shared_with_user_id,
        permission=body.permission,
        token=secrets.token_urlsafe(32),
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)

    logger.info(f"Shared conversation {conv_uuid} with user {body.shared_with_user_id} (perm={body.permission})")
    return ShareResponse.model_validate(share)


@router.delete("/{conversation_id}/share/{share_id}")
async def revoke_share(
    conversation_id: str,
    share_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Revoke a conversation share."""
    conv_uuid = _parse_uuid(conversation_id)
    share_uuid = _parse_uuid(share_id)

    result = await db.execute(
        select(ConversationShare).where(
            ConversationShare.id == share_uuid,
            ConversationShare.conversation_id == conv_uuid,
        )
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    share.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(f"Revoked share {share_id} for conversation {conversation_id}")
    return {"status": "revoked", "id": share_id}


# ─── Share token resolution (separate router, no /v1/conversations prefix) ────

share_router = APIRouter(prefix="/v1/share", tags=["conversations"], dependencies=[Depends(verify_api_key)])


@share_router.get("/{token}", response_model=ConversationResponse)
async def resolve_share_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Resolve a share token to its conversation."""
    result = await db.execute(
        select(ConversationShare).where(
            ConversationShare.token == token,
            ConversationShare.revoked_at.is_(None),
        )
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(status_code=404, detail="Invalid or revoked share link")

    conv = await db.get(Conversation, share.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationResponse.model_validate(conv)
