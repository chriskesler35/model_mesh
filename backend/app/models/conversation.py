"""Conversation and Message models."""

import uuid as _uuid
from sqlalchemy import Column, String, ForeignKey, Text, Integer, Numeric, JSON, Boolean, DateTime
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from app.models.base import BaseMixin


class UUIDType(TypeDecorator):
    """SQLite-compatible UUID stored as CHAR(36)."""
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _uuid.UUID(str(value))
        except ValueError:
            return value


class Conversation(Base, BaseMixin):
    """Conversation for message history."""
    __tablename__ = "conversations"

    persona_id = Column(UUIDType, ForeignKey("personas.id", ondelete="SET NULL"))
    external_id = Column(String(100), unique=True, nullable=True)
    extra_data = Column("metadata", JSON, default=dict)

    # Session management fields
    title = Column(String(200), nullable=True)
    pinned = Column(Boolean, default=False, nullable=False)
    keep_forever = Column(Boolean, default=False, nullable=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    message_count = Column(Integer, default=0, nullable=False)

    # Relationships
    persona = relationship("Persona", backref="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Conversation {self.id} title={self.title!r}>"


class Message(Base, BaseMixin):
    """Message in a conversation."""
    __tablename__ = "messages"

    conversation_id = Column(UUIDType, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    model_used = Column(UUIDType, ForeignKey("models.id", ondelete="SET NULL"))
    tokens_in = Column(Integer)
    tokens_out = Column(Integer)
    latency_ms = Column(Integer)
    estimated_cost = Column(Numeric(10, 6), default=0)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    model = relationship("Model")

    def __repr__(self):
        return f"<Message {self.id} ({self.role})>"
