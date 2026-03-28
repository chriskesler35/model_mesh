"""Persona model for AI personas."""

from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import BaseMixin
from datetime import datetime


class Persona(Base, BaseMixin):
    """Persona configuration for routing and prompts."""
    __tablename__ = "personas"
    
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text)
    system_prompt = Column(Text)
    primary_model_id = Column(UUID(as_uuid=True), ForeignKey("models.id", ondelete="SET NULL"))
    fallback_model_id = Column(UUID(as_uuid=True), ForeignKey("models.id", ondelete="SET NULL"))
    routing_rules = Column(JSON, default=dict)
    memory_enabled = Column(Boolean, default=True)
    max_memory_messages = Column(Integer, default=10)
    is_default = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    primary_model = relationship("Model", foreign_keys=[primary_model_id])
    fallback_model = relationship("Model", foreign_keys=[fallback_model_id])
    
    def __repr__(self):
        return f"<Persona {self.name}>"