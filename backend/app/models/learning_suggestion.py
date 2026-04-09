"""Learning suggestion model for routing auto-tuning."""

import uuid as _uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Text, DateTime
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
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _uuid.UUID(str(value))


class LearningSuggestion(Base, BaseMixin):
    """Auto-tuning suggestions derived from feedback analysis."""
    __tablename__ = "learning_suggestions"

    suggestion_type = Column(String(50), nullable=False)  # e.g. "model_preference"
    model_id = Column(String(200), nullable=False, index=True)
    task_type = Column(String(100), nullable=True, index=True)
    confidence = Column(Float, nullable=False)
    reason = Column(Text, nullable=False)
    current_value = Column(Text, nullable=True)
    suggested_value = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="pending", index=True)
    applied_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "suggestion_type": self.suggestion_type,
            "model_id": self.model_id,
            "task_type": self.task_type,
            "confidence": self.confidence,
            "reason": self.reason,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "status": self.status,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<LearningSuggestion {self.id} type={self.suggestion_type} status={self.status}>"
