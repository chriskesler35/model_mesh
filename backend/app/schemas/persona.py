"""Persona schemas."""

from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, UUID4, field_validator
from datetime import datetime
import uuid


class RoutingRules(BaseModel):
    """Routing rules for a persona."""
    max_cost: Optional[float] = None
    prefer_local: Optional[bool] = False
    timeout_seconds: Optional[int] = 60
    max_tokens: Optional[int] = 4096
    auto_route: Optional[bool] = False
    classifier_persona_id: Optional[str] = None  # ID of persona to use for classification


class PersonaBase(BaseModel):
    """Base persona schema."""
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    primary_model_id: Optional[UUID4] = None
    fallback_model_id: Optional[UUID4] = None
    routing_rules: RoutingRules = RoutingRules()
    memory_enabled: bool = True
    max_memory_messages: int = 10


class PersonaCreate(PersonaBase):
    """Schema for creating a persona."""
    pass


class PersonaUpdate(BaseModel):
    """Schema for updating a persona."""
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    primary_model_id: Optional[Union[UUID4, str]] = None
    fallback_model_id: Optional[Union[UUID4, str]] = None
    routing_rules: Optional[RoutingRules] = None
    memory_enabled: Optional[bool] = None
    max_memory_messages: Optional[int] = None
    is_default: Optional[bool] = None

    @field_validator('primary_model_id', 'fallback_model_id', mode='before')
    @classmethod
    def coerce_uuid(cls, v):
        if v == '' or v is None:
            return None
        try:
            return uuid.UUID(str(v))
        except (ValueError, AttributeError):
            return None


class PersonaResponse(PersonaBase):
    """Schema for persona response."""
    id: UUID4
    is_default: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PersonaList(BaseModel):
    """Paginated persona list."""
    data: list[PersonaResponse]
    total: int
    limit: int
    offset: int
    has_more: bool