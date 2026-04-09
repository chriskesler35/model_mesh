"""Agent memory model for persisting run context across agent executions."""

import uuid as _uuid
from sqlalchemy import Column, String, Text, DateTime, Index
from sqlalchemy.types import CHAR
from sqlalchemy.sql import func
from app.database import Base


class AgentMemory(Base):
    """Stores agent run outputs for memory-enabled agents.

    Each entry captures the task and output summary from a single agent run,
    allowing future runs to reference prior context.
    """
    __tablename__ = "agent_memory"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    agent_id = Column(CHAR(36), nullable=False, index=True)
    run_id = Column(CHAR(36), nullable=True)
    task = Column(Text, nullable=False)
    output_summary = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Composite index for the common query pattern: fetch recent memories per agent
    __table_args__ = (
        Index("ix_agent_memory_agent_created", "agent_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "task": self.task,
            "output_summary": self.output_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
