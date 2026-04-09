"""Custom method model for user-created development methodologies.

Custom methods appear alongside built-in methods (BMAD, GSD, SuperPowers)
and define their own phases for multi-agent pipeline execution.
"""

import uuid as _uuid
from sqlalchemy import Column, String, Text, JSON, DateTime, Boolean
from sqlalchemy.types import CHAR
from sqlalchemy.sql import func
from app.database import Base


class CustomMethod(Base):
    """A user-created development methodology with custom phases."""
    __tablename__ = "custom_methods"

    id               = Column(CHAR(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    user_id          = Column(String(100), nullable=True)           # owner (nullable for single-user mode)
    name             = Column(String(200), unique=True, nullable=False)
    description      = Column(Text, nullable=True)
    phases           = Column(JSON, nullable=False)                 # [{name, role, default_model, system_prompt, artifact_type, depends_on}]
    trigger_keywords = Column(JSON, nullable=True)                  # ["keyword1", "keyword2"] for auto-detection
    is_active        = Column(Boolean, default=True, nullable=False)
    created_at       = Column(DateTime, server_default=func.now())
    updated_at       = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id":               self.id,
            "user_id":          self.user_id,
            "name":             self.name,
            "description":      self.description,
            "phases":           self.phases or [],
            "trigger_keywords": self.trigger_keywords or [],
            "is_active":        self.is_active,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
            "updated_at":       self.updated_at.isoformat() if self.updated_at else None,
        }
