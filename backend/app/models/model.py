"""Model model for AI models."""

from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, Numeric, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.models.base import Base


class Model(Base):
    """AI model configuration."""
    __tablename__ = "models"
    
    provider_id = Column(UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False)
    model_id = Column(String(200), nullable=False)  # External model ID
    display_name = Column(String(200))
    cost_per_1m_input = Column(Numeric(10, 6), default=0)
    cost_per_1m_output = Column(Numeric(10, 6), default=0)
    context_window = Column(Integer)
    capabilities = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    provider = relationship("Provider", backref="models")
    
    __table_args__ = (
        CheckConstraint("context_window > 0 OR context_window IS NULL", name="check_context_window_positive"),
    )
    
    def __repr__(self):
        return f"<Model {self.model_id}>"