"""Model model for AI models."""

from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, Numeric, CheckConstraint, JSON, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.base import BaseMixin


class Model(Base, BaseMixin):
    """AI model configuration."""
    __tablename__ = "models"
    
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False)
    model_id = Column(String(200), nullable=False)  # External model ID
    display_name = Column(String(200))
    cost_per_1m_input = Column(Numeric(10, 6), default=0)
    cost_per_1m_output = Column(Numeric(10, 6), default=0)
    context_window = Column(Integer)
    capabilities = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    validation_status = Column(String(20), default="unverified", nullable=False)  # validated | unverified | failed
    validated_at = Column(DateTime, nullable=True)
    validation_source = Column(String(50), nullable=True)
    validation_warning = Column(String(500), nullable=True)
    validation_error = Column(String(500), nullable=True)
    
    # Relationships
    provider = relationship("Provider", backref="models")
    
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="uq_models_provider_model_id"),
        CheckConstraint("context_window > 0 OR context_window IS NULL", name="check_context_window_positive"),
    )
    
    def __repr__(self):
        return f"<Model {self.model_id}>"
