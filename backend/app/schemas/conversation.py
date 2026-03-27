"""Conversation schemas."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, UUID4
from datetime import datetime


class ConversationCreate(BaseModel):
    """Schema for creating a conversation."""
    persona_id: Optional[UUID4] = None
    external_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


class ConversationResponse(BaseModel):
    """Schema for conversation response."""
    id: UUID4
    persona_id: Optional[UUID4] = None
    external_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationList(BaseModel):
    """Paginated conversation list."""
    data: list[ConversationResponse]
    total: int
    limit: int
    offset: int
    has_more: bool


class MessageResponse(BaseModel):
    """Schema for message response."""
    id: UUID4
    conversation_id: UUID4
    role: str
    content: str
    model_used: Optional[UUID4] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: Optional[int] = None
    estimated_cost: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MessageList(BaseModel):
    """Paginated message list."""
    data: list[MessageResponse]
    total: int
    limit: int
    offset: int
    has_more: bool