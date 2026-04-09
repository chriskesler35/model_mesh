"""Feedback model for user satisfaction tracking."""

import uuid as _uuid
from sqlalchemy import Column, String, Integer, Text
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


class Feedback(Base, BaseMixin):
    """User feedback on AI responses (thumbs up/down)."""
    __tablename__ = "feedback"

    user_id = Column(String(100), nullable=True)
    message_id = Column(String(36), nullable=False, index=True)
    conversation_id = Column(String(36), nullable=True, index=True)
    model_id = Column(String(200), nullable=True, index=True)
    rating = Column(Integer, nullable=False)  # 1 = thumbs down, 5 = thumbs up
    feedback_text = Column(Text, nullable=True)

    def __repr__(self):
        return f"<Feedback {self.id} rating={self.rating}>"
