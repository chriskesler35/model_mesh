"""Provider model for AI service providers."""

from sqlalchemy import Column, String, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base
from app.models.base import BaseMixin


class Provider(Base, BaseMixin):
    """AI service provider (Ollama, Anthropic, Google)."""
    __tablename__ = "providers"
    
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200))
    api_base_url = Column(String(500))
    auth_type = Column(String(50), default="none")  # 'bearer', 'api_key', 'none'
    config = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<Provider {self.name}>"