"""Conversation and Message models."""

from sqlalchemy import Column, String, ForeignKey, Text, Integer, Numeric
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import BaseMixin


class Conversation(Base, BaseMixin):
    """Conversation for message history."""
    __tablename__ = "conversations"
    
    persona_id = Column(UUID(as_uuid=True), ForeignKey("personas.id", ondelete="SET NULL"))
    external_id = Column(String(100), unique=True, nullable=True)  # Client-provided ID
    extra_data = Column("metadata", JSONB, default=dict)  # Renamed to avoid SQLAlchemy conflict
    
    # Relationships
    persona = relationship("Persona", backref="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Conversation {self.id}>"


class Message(Base, BaseMixin):
    """Message in a conversation."""
    __tablename__ = "messages"
    
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    model_used = Column(UUID(as_uuid=True), ForeignKey("models.id", ondelete="SET NULL"))
    tokens_in = Column(Integer)
    tokens_out = Column(Integer)
    latency_ms = Column(Integer)
    estimated_cost = Column(Numeric(10, 6), default=0)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    model = relationship("Model")
    
    def __repr__(self):
        return f"<Message {self.id} ({self.role})>"