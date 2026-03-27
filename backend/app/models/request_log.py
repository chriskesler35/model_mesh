"""Request log model for analytics."""

from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, Text, Numeric
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base


class RequestLog(Base):
    """Request log for analytics and cost tracking."""
    __tablename__ = "request_logs"
    
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"))
    persona_id = Column(UUID(as_uuid=True), ForeignKey("personas.id", ondelete="SET NULL"))
    model_id = Column(UUID(as_uuid=True), ForeignKey("models.id", ondelete="SET NULL"))
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL"))
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    latency_ms = Column(Integer)
    estimated_cost = Column(Numeric(10, 6), default=0)
    success = Column(Boolean)
    error_message = Column(Text)  # Sanitized error (no sensitive data)
    
    def __repr__(self):
        return f"<RequestLog {self.id}>"