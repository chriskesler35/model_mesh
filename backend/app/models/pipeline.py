"""Multi-agent pipeline models — Option A orchestration.

A Pipeline runs a task through N phases (Analyst, Architect, Coder, etc.)
Each phase is a PhaseRun with its own agent role, model, and structured
artifact output. Phases gate on user approval unless auto_approve is set.
"""

import uuid as _uuid
from sqlalchemy import Column, String, Text, JSON, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.types import CHAR
from sqlalchemy.sql import func
from app.database import Base


class Pipeline(Base):
    """A multi-agent pipeline run attached to a workbench session."""
    __tablename__ = "workbench_pipelines"

    id                  = Column(CHAR(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    session_id          = Column(CHAR(36), ForeignKey("workbench_sessions.id", ondelete="CASCADE"), nullable=False)
    method_id           = Column(String(50), nullable=False)      # 'bmad', 'gsd', 'superpowers'
    phases              = Column(JSON, nullable=False)             # [{name, role, model, system_prompt, artifact_type}]
    current_phase_index = Column(Integer, default=0, nullable=False)
    status              = Column(String(30), default="pending")    # pending, running, awaiting_approval, completed, failed, cancelled
    auto_approve        = Column(Boolean, default=False, nullable=False)
    initial_task        = Column(Text, nullable=False)
    created_at          = Column(DateTime, server_default=func.now())
    completed_at        = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id":                  self.id,
            "session_id":          self.session_id,
            "method_id":           self.method_id,
            "phases":              self.phases or [],
            "current_phase_index": self.current_phase_index,
            "status":              self.status,
            "auto_approve":        self.auto_approve,
            "initial_task":        self.initial_task,
            "created_at":          self.created_at.isoformat() if self.created_at else None,
            "completed_at":        self.completed_at.isoformat() if self.completed_at else None,
        }


class PhaseRun(Base):
    """One phase of a pipeline's execution — persisted for replay + audit."""
    __tablename__ = "workbench_phase_runs"

    id              = Column(CHAR(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    pipeline_id     = Column(CHAR(36), ForeignKey("workbench_pipelines.id", ondelete="CASCADE"), nullable=False)
    phase_index     = Column(Integer, nullable=False)
    phase_name      = Column(String(100), nullable=False)
    agent_role      = Column(String(100), nullable=False)       # "Business Analyst", "Architect", etc.
    model_id        = Column(String(200), nullable=True)
    status          = Column(String(30), default="pending")     # pending, running, awaiting_approval, approved, rejected, failed, skipped
    input_context   = Column(JSON, nullable=True)                # prior phase artifacts passed in
    output_artifact = Column(JSON, nullable=True)                # structured output of this phase
    raw_response    = Column(Text, nullable=True)                # full LLM response text
    user_feedback   = Column(Text, nullable=True)                # feedback when rejected
    input_tokens    = Column(Integer, nullable=True)
    output_tokens   = Column(Integer, nullable=True)
    started_at      = Column(DateTime, nullable=True)
    completed_at    = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id":              self.id,
            "pipeline_id":     self.pipeline_id,
            "phase_index":     self.phase_index,
            "phase_name":      self.phase_name,
            "agent_role":      self.agent_role,
            "model_id":        self.model_id,
            "status":          self.status,
            "input_context":   self.input_context,
            "output_artifact": self.output_artifact,
            "raw_response":    self.raw_response,
            "user_feedback":   self.user_feedback,
            "input_tokens":    self.input_tokens,
            "output_tokens":   self.output_tokens,
            "started_at":      self.started_at.isoformat() if self.started_at else None,
            "completed_at":    self.completed_at.isoformat() if self.completed_at else None,
            "created_at":      self.created_at.isoformat() if self.created_at else None,
        }
