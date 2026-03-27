"""Base model with common columns."""

from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declared_attr
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime


class Base:
    """Base model with common columns."""
    
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)