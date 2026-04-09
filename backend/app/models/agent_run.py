"""AgentRun model — stores history of agent executions."""

from sqlalchemy import Column, String, Text, Integer, JSON, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import BaseMixin


class AgentRun(Base, BaseMixin):
    """Record of a single agent execution."""
    __tablename__ = "agent_runs"

    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True)
    task = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="running")  # running, completed, failed, timeout
    output = Column(Text, default="")
    tool_log = Column(JSON, default=list)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)

    def to_dict(self, truncate_output: bool = False):
        import uuid as _uuid
        from datetime import datetime
        d = {}
        for f in ['id', 'agent_id', 'task', 'status', 'output', 'tool_log',
                   'input_tokens', 'output_tokens', 'duration_ms', 'created_at', 'updated_at']:
            val = getattr(self, f, None)
            if isinstance(val, _uuid.UUID):
                val = str(val)
            if isinstance(val, datetime):
                val = val.isoformat()
            d[f] = val
        if truncate_output and d.get('output') and len(d['output']) > 200:
            d['output'] = d['output'][:200] + '...'
        return d

    def __repr__(self):
        return f"<AgentRun {self.id} agent={self.agent_id} status={self.status}>"
