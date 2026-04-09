"""Conversation schemas."""

from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, UUID4
from datetime import datetime


class ConversationCreate(BaseModel):
    """Schema for creating a conversation."""
    persona_id: Optional[UUID4] = None
    external_id: Optional[str] = None
    extra_data: Dict[str, Any] = {}
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    """Schema for updating a conversation."""
    title: Optional[str] = None
    pinned: Optional[bool] = None
    keep_forever: Optional[bool] = None


class ConversationResponse(BaseModel):
    """Schema for conversation response."""
    id: UUID4
    persona_id: Optional[UUID4] = None
    external_id: Optional[str] = None
    extra_data: Dict[str, Any] = {}
    title: Optional[str] = None
    pinned: bool = False
    keep_forever: bool = False
    last_message_at: Optional[datetime] = None
    message_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

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
    image_url: Optional[str] = None
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


# ─── Share schemas ────────────────────────────────────────────────────────────

class ShareCreate(BaseModel):
    """Schema for creating a conversation share."""
    shared_with_user_id: str
    permission: Literal["read", "write"] = "read"


class ShareResponse(BaseModel):
    """Schema for share response."""
    id: UUID4
    conversation_id: UUID4
    shared_with_user_id: str
    permission: str
    token: str
    created_at: datetime
    revoked_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SharedConversationResponse(BaseModel):
    """A conversation that was shared with the current user."""
    share_id: UUID4
    conversation_id: UUID4
    permission: str
    token: str
    shared_at: datetime
    conversation: ConversationResponse


class SharedConversationList(BaseModel):
    """List of conversations shared with the current user."""
    data: list[SharedConversationResponse]
    total: int
