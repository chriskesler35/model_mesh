"""WorkbenchSession model — persists agent sessions across restarts."""

import uuid as _uuid
from sqlalchemy import Column, String, Text, JSON, DateTime
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


class WorkbenchSession(Base):
    """Persisted workbench agent session."""
    __tablename__ = "workbench_sessions"

    id           = Column(CHAR(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    task         = Column(Text, nullable=False)
    agent_type   = Column(String(50), default="coder")
    model        = Column(String(200))
    project_id   = Column(CHAR(36), nullable=True)
    project_path = Column(Text, nullable=True)
    status       = Column(String(20), default="pending")   # pending|running|completed|failed|cancelled
    files        = Column(JSON, default=list)              # list of relative paths written
    created_at   = Column(DateTime, server_default=func.now())
    started_at   = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id":           self.id,
            "task":         self.task,
            "agent_type":   self.agent_type,
            "model":        self.model,
            "project_id":   self.project_id,
            "project_path": self.project_path,
            "status":       self.status,
            "files":        self.files or [],
            "created_at":   self.created_at.isoformat() if self.created_at else None,
            "started_at":   self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
