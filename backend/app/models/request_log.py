"""Request log model for analytics."""

import uuid as _uuid
from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, Text, Numeric
from sqlalchemy.types import TypeDecorator, CHAR
from app.database import Base
from app.models.base import BaseMixin


class UUIDType(TypeDecorator):
    """Platform-independent UUID type. Stores as CHAR(36) string for SQLite compatibility."""
    impl = CHAR(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, _uuid.UUID):
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _uuid.UUID(str(value))


class RequestLog(Base, BaseMixin):
    """Request log for analytics and cost tracking."""
    __tablename__ = "request_logs"

    conversation_id = Column(UUIDType, ForeignKey("conversations.id", ondelete="SET NULL"))
    persona_id = Column(UUIDType, ForeignKey("personas.id", ondelete="SET NULL"))
    model_id = Column(UUIDType, ForeignKey("models.id", ondelete="SET NULL"))
    provider_id = Column(UUIDType, ForeignKey("providers.id", ondelete="SET NULL"))
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    latency_ms = Column(Integer)
    estimated_cost = Column(Numeric(10, 6), default=0)
    success = Column(Boolean)
    error_message = Column(Text)  # Sanitized error (no sensitive data)
    
    def __repr__(self):
        return f"<RequestLog {self.id}>"