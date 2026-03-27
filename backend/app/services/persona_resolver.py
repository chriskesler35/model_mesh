"""Persona resolver for finding personas and models."""

from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Persona, Model, Provider
import uuid


class PersonaResolver:
    """Resolve persona name/ID to model and routing configuration."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def resolve(self, persona_ref: str) -> Tuple[Optional[Persona], Optional[Model], Optional[Model]]:
        """
        Resolve persona reference (name or ID) to persona and models.
        Returns: (persona, primary_model, fallback_model)
        """
        # Try as UUID first
        try:
            persona_id = uuid.UUID(persona_ref)
            persona = await self._get_by_id(persona_id)
        except ValueError:
            # Not a UUID, try as name
            persona = await self._get_by_name(persona_ref)
        
        if not persona:
            return None, None, None
        
        # Get models
        primary_model = None
        fallback_model = None
        
        if persona.primary_model_id:
            primary_model = await self._get_model(persona.primary_model_id)
        
        if persona.fallback_model_id:
            fallback_model = await self._get_model(persona.fallback_model_id)
        
        return persona, primary_model, fallback_model
    
    async def _get_by_id(self, persona_id) -> Optional[Persona]:
        result = await self.db.execute(
            select(Persona).where(Persona.id == persona_id)
        )
        return result.scalar_one_or_none()
    
    async def _get_by_name(self, name: str) -> Optional[Persona]:
        result = await self.db.execute(
            select(Persona).where(Persona.name == name)
        )
        return result.scalar_one_or_none()
    
    async def _get_model(self, model_id) -> Optional[Model]:
        result = await self.db.execute(
            select(Model).where(Model.id == model_id)
        )
        return result.scalar_one_or_none()
    
    async def get_default_persona(self) -> Optional[Persona]:
        """Get the default persona."""
        result = await self.db.execute(
            select(Persona).where(Persona.is_default == True)
        )
        return result.scalar_one_or_none()