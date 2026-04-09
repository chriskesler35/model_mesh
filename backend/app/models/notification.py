"""Notification model for @mention alerts and other notifications."""

import uuid as _uuid
from sqlalchemy import Column, String, Text, Boolean
from sqlalchemy.types import TypeDecorator, CHAR
from app.database import Base
from app.models.base import BaseMixin


class UUIDType(TypeDecorator):
    """Platform-independent UUID type. Stores as CHAR(36) for SQLite compatibility."""
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


class Notification(Base, BaseMixin):
    """User notification (mentions, system alerts, etc.)."""
    __tablename__ = "notifications"

    user_id = Column(String(100), nullable=False, index=True)
    type = Column(String(50), nullable=False, default="mention")  # mention, system, etc.
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=True)
    conversation_id = Column(String(36), nullable=True, index=True)
    message_id = Column(String(36), nullable=True)
    read = Column(Boolean, default=False, nullable=False, index=True)

    def __repr__(self):
        return f"<Notification {self.id} user={self.user_id} type={self.type} read={self.read}>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "read": self.read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
