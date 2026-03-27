"""Conversation endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import uuid
from app.database import get_db
from app.models import Conversation, Message
from app.schemas import ConversationCreate, ConversationResponse, ConversationList, MessageResponse, MessageList
from app.middleware.auth import verify_api_key

router = APIRouter(prefix="/v1/conversations", tags=["conversations"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=ConversationList)
async def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """List all conversations."""
    query = select(Conversation).order_by(Conversation.created_at.desc())
    
    # Get total count
    count_query = select(func.count()).select_from(Conversation)
    total = await db.scalar(count_query)
    
    # Get paginated results
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
    db_conversation = Conversation(**conversation.model_dump())
    db.add(db_conversation)
    await db.commit()
    await db.refresh(db_conversation)
    
    return ConversationResponse.model_validate(db_conversation)


@router.get("/{conversation_id}/messages", response_model=MessageList)
async def get_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Get messages for a conversation."""
    conv_uuid = uuid.UUID(conversation_id)
    
    # Check conversation exists
    conv = await db.get(Conversation, conv_uuid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get messages
    query = select(Message).where(
        Message.conversation_id == conv_uuid
    ).order_by(Message.created_at.asc())
    
    # Get total count
    count_query = select(func.count()).select_from(Message).where(
        Message.conversation_id == conv_uuid
    )
    total = await db.scalar(count_query)
    
    # Get paginated results
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


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a conversation."""
    conv_uuid = uuid.UUID(conversation_id)
    
    conv = await db.get(Conversation, conv_uuid)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    await db.delete(conv)
    await db.commit()
    
    return {"status": "deleted"}