"""Per-session command execution log — audit trail of every CMD: the agent emitted."""

import uuid as _uuid
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Boolean
from sqlalchemy.types import CHAR
from sqlalchemy.sql import func
from app.database import Base


class CommandExecution(Base):
    """Audit record for a single CMD: block emitted by a workbench agent.

    Captures the tier, approval state, exit code, truncated stdout/stderr,
    timestamps. Used for the session command log + approval queue.
    """
    __tablename__ = "workbench_commands"

    id              = Column(CHAR(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    session_id      = Column(CHAR(36), ForeignKey("workbench_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    pipeline_id     = Column(CHAR(36), nullable=True, index=True)  # set when emitted from a pipeline phase
    phase_run_id    = Column(CHAR(36), nullable=True, index=True)  # set when emitted from a pipeline phase
    turn_number     = Column(Integer, nullable=True)
    command         = Column(Text, nullable=False)
    tier            = Column(String(20), nullable=False)  # auto | notice | approval | blocked
    status          = Column(String(20), default="pending", nullable=False)  # pending | approved | rejected | running | completed | failed | skipped | bypassed
    exit_code       = Column(Integer, nullable=True)
    stdout          = Column(Text, nullable=True)
    stderr          = Column(Text, nullable=True)
    user_feedback   = Column(Text, nullable=True)  # set when user rejects with a reason
    bypass_used     = Column(Boolean, default=False, nullable=False)  # true if ran via bypass mode
    duration_ms     = Column(Integer, nullable=True)
    created_at      = Column(DateTime, server_default=func.now())
    started_at      = Column(DateTime, nullable=True)
    completed_at    = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id":            self.id,
            "session_id":    self.session_id,
            "pipeline_id":   self.pipeline_id,
            "phase_run_id":  self.phase_run_id,
            "turn_number":   self.turn_number,
            "command":       self.command,
            "tier":          self.tier,
            "status":        self.status,
            "exit_code":     self.exit_code,
            "stdout":        self.stdout,
            "stderr":        self.stderr,
            "user_feedback": self.user_feedback,
            "bypass_used":   self.bypass_used,
            "duration_ms":   self.duration_ms,
            "created_at":    self.created_at.isoformat() if self.created_at else None,
            "started_at":    self.started_at.isoformat() if self.started_at else None,
            "completed_at":  self.completed_at.isoformat() if self.completed_at else None,
        }
