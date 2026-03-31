"""App-level settings stored in database (key/value)."""

from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base


class AppSetting(Base):
    """Key-value store for app configuration."""
    __tablename__ = "app_settings"

    key        = Column(String(200), primary_key=True)
    value      = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
