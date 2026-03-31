"""Learned Preference model — stores user preferences detected from chat."""

import uuid as _uuid
from sqlalchemy import Column, String, Text, Boolean, DateTime
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.sql import func
from app.database import Base


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


class Preference(Base):
    """A learned user preference."""
    __tablename__ = "preferences"

    id         = Column(CHAR(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    key        = Column(String(200), nullable=False)           # e.g. "coding_style", "response_format"
    value      = Column(Text, nullable=False)                  # e.g. "Prefers bullet points over paragraphs"
    category   = Column(String(100), default="general")        # general, coding, communication, ui, workflow
    source     = Column(String(50), default="detected")        # detected (from chat), manual (user added)
    is_active  = Column(Boolean, default=True)                 # user can toggle off without deleting
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id":         str(self.id),
            "key":        self.key,
            "value":      self.value,
            "category":   self.category,
            "source":     self.source,
            "is_active":  self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
