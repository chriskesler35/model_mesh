"""Encrypted OAuth credential storage."""

import uuid as _uuid
from sqlalchemy import Column, String, Text, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class OAuthCredential(Base):
    """Stores encrypted provider OAuth tokens keyed by local user id."""

    __tablename__ = "oauth_credentials"

    id = Column(String(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    user_id = Column(String(64), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    access_token_encrypted = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_oauth_credentials_user_provider"),
    )
