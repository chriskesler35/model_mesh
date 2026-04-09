"""Conversation share model for shared conversation access."""

import secrets
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import BaseMixin
from app.models.conversation import UUIDType


class ConversationShare(Base, BaseMixin):
    """Tracks shared access to conversations."""
    __tablename__ = "conversation_shares"

    conversation_id = Column(UUIDType, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_with_user_id = Column(String(100), nullable=False, index=True)
    permission = Column(String(10), nullable=False, default="read")  # 'read' or 'write'
    token = Column(String(100), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation = relationship("Conversation", backref="shares")

    def __repr__(self):
        return f"<ConversationShare {self.id} conv={self.conversation_id} user={self.shared_with_user_id} perm={self.permission}>"
