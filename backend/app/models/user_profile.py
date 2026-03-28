"""User profile and memory system models."""

from sqlalchemy import Column, String, Text, Boolean, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import BaseMixin
from datetime import datetime
import uuid


class UserProfile(Base, BaseMixin):
    """User profile for personalization."""
    __tablename__ = "user_profiles"

    name = Column(String(255), nullable=False, default="User")
    email = Column(String(255), nullable=True)
    preferences = Column(JSON, default=dict)  # {"tone": "concise", "verbosity": "low", ...}
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<UserProfile {self.name}>"


class MemoryFile(Base, BaseMixin):
    """Memory files like USER.md, CONTEXT.md, PREFERENCES.md."""
    __tablename__ = "memory_files"

    user_id = Column(UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"))
    name = Column(String(255), nullable=False)  # USER.md, CONTEXT.md, etc.
    content = Column(Text, nullable=False, default="")
    description = Column(String(500), nullable=True)

    def __repr__(self):
        return f"<MemoryFile {self.name}>"


class PreferenceTracking(Base, BaseMixin):
    """Track learned preferences from chat interactions."""
    __tablename__ = "preference_tracking"

    user_id = Column(UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"))
    key = Column(String(255), nullable=False)  # "preferred_language", "coding_style", etc.
    value = Column(Text, nullable=False)
    source = Column(String(50), nullable=False)  # "chat", "manual", "system"
    confidence = Column(String(20), default="medium")  # low, medium, high
    context = Column(Text, nullable=True)  # The conversation context where this was learned

    def __repr__(self):
        return f"<PreferenceTracking {self.key}={self.value}>"


class SystemModification(Base, BaseMixin):
    """Track system modifications made through chat."""
    __tablename__ = "system_modifications"

    user_id = Column(UUID(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"))
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"))
    modification_type = Column(String(50), nullable=False)  # "add_model", "update_persona", etc.
    entity_type = Column(String(50), nullable=False)  # "model", "persona", "memory_file"
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    before_value = Column(JSON, nullable=True)
    after_value = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)  # Why this change was made

    def __repr__(self):
        return f"<SystemModification {self.modification_type}>"