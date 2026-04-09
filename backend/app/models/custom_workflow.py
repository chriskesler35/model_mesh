"""Custom workflow model for user-saved workflow builder designs."""

import uuid as _uuid
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.types import CHAR
from sqlalchemy.sql import func
from app.database import Base


class CustomWorkflow(Base):
    """A user-saved workflow (nodes + edges + positions) from the builder."""
    __tablename__ = "custom_workflows"

    id          = Column(CHAR(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    user_id     = Column(String(100), nullable=True)
    name        = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    graph_data  = Column(JSON, nullable=False)  # {nodes: [...], edges: [...]}
    created_at  = Column(DateTime, server_default=func.now())
    updated_at  = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id":          self.id,
            "user_id":     self.user_id,
            "name":        self.name,
            "description": self.description,
            "graph_data":  self.graph_data or {},
            "created_at":  self.created_at.isoformat() if self.created_at else None,
            "updated_at":  self.updated_at.isoformat() if self.updated_at else None,
        }
