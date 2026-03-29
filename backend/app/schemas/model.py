"""Model schemas."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, UUID4
from datetime import datetime


class ModelBase(BaseModel):
    """Base model schema."""
    model_id: str
    display_name: Optional[str] = None
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    context_window: Optional[int] = None
    capabilities: Dict[str, Any] = {}
    is_active: bool = True


class ModelCreate(ModelBase):
    """Schema for creating a model."""
    provider_id: UUID4


class ModelUpdate(BaseModel):
    """Schema for updating a model."""
    model_id: Optional[str] = None
    display_name: Optional[str] = None
    cost_per_1m_input: Optional[float] = None
    cost_per_1m_output: Optional[float] = None
    context_window: Optional[int] = None
    capabilities: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ModelResponse(ModelBase):
    """Schema for model response."""
    id: UUID4
    provider_id: UUID4
    provider_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ModelList(BaseModel):
    """Paginated model list."""
    data: list[ModelResponse]
    total: int
    limit: int
    offset: int
    has_more: bool