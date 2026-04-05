"""WorkbenchSession model — persists agent sessions across restarts."""

import uuid as _uuid
from sqlalchemy import Column, String, Text, JSON, DateTime, Integer, Numeric, Boolean
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
    pipeline_id  = Column(CHAR(36), nullable=True, index=True)  # link to active pipeline (Option A)
    status       = Column(String(20), default="pending")   # pending|running|completed|failed|cancelled
    files        = Column(JSON, default=list)              # list of relative paths written
    events_log   = Column(JSON, default=list)              # all events for replay
    messages     = Column(JSON, default=list)              # conversation history [{role, content}]
    input_tokens  = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Numeric(10, 6), nullable=True)
    bypass_approvals = Column(Boolean, default=False, nullable=False)  # YOLO mode: skip all approval gates
    created_at   = Column(DateTime, server_default=func.now())
    started_at   = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id":             self.id,
            "task":           self.task,
            "agent_type":     self.agent_type,
            "model":          self.model,
            "project_id":     self.project_id,
            "project_path":   self.project_path,
            "pipeline_id":    self.pipeline_id,
            "status":         self.status,
            "files":          self.files or [],
            "events_log":     self.events_log or [],
            "messages":       self.messages or [],
            "input_tokens":   self.input_tokens,
            "output_tokens":  self.output_tokens,
            "estimated_cost": float(self.estimated_cost) if self.estimated_cost is not None else None,
            "bypass_approvals": bool(self.bypass_approvals) if self.bypass_approvals is not None else False,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
            "started_at":     self.started_at.isoformat() if self.started_at else None,
            "completed_at":   self.completed_at.isoformat() if self.completed_at else None,
        }
