"""Persona schemas."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, UUID4
from datetime import datetime


class RoutingRules(BaseModel):
    """Routing rules for a persona."""
    max_cost: Optional[float] = None
    prefer_local: Optional[bool] = False
    timeout_seconds: Optional[int] = 60
    max_tokens: Optional[int] = 4096


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
    primary_model_id: Optional[UUID4] = None
    fallback_model_id: Optional[UUID4] = None
    routing_rules: Optional[RoutingRules] = None
    memory_enabled: Optional[bool] = None
    max_memory_messages: Optional[int] = None
    is_default: Optional[bool] = None


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