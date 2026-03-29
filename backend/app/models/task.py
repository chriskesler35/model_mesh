"""Background task model."""

import uuid as _uuid
from sqlalchemy import Column, String, Text, Integer, JSON, DateTime
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.sql import func
from app.database import Base
from app.models.base import BaseMixin


class UUIDType(TypeDecorator):
    """SQLite-compatible UUID."""
    impl = CHAR(36)
    cache_ok = True
    def process_bind_param(self, value, dialect):
        return str(value) if value else None
    def process_result_value(self, value, dialect):
        return _uuid.UUID(str(value)) if value else None


class Task(Base, BaseMixin):
    """Background task for async processing (image gen, agent runs, etc.)."""
    __tablename__ = "tasks"

    task_type = Column(String(50), nullable=False)          # "image_gen", "agent_run", etc.
    status = Column(String(20), nullable=False, default="pending")  # pending, running, completed, failed
    params = Column(JSON, default=dict)                     # input params (prompt, model, etc.)
    result = Column(JSON, nullable=True)                    # output data (image url, etc.)
    error = Column(Text, nullable=True)                     # error message if failed
    progress = Column(Integer, default=0)                   # 0-100
    user_message = Column(String(500), nullable=True)       # human-readable status
    conversation_id = Column(String(36), nullable=True)     # link back to chat if applicable
    acknowledged = Column(Integer, default=0)               # 0=unread, 1=seen by user

    def __repr__(self):
        return f"<Task {self.id} type={self.task_type} status={self.status}>"
