"""Persona endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models import Persona
from app.schemas import PersonaCreate, PersonaUpdate, PersonaResponse, PersonaList
from app.middleware.auth import verify_api_key
import uuid as _uuid

router = APIRouter(prefix="/v1/personas", tags=["personas"], dependencies=[Depends(verify_api_key)])


def _parse_uuid(value: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Not found")


@router.get("", response_model=PersonaList)
async def list_personas(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """List all personas."""
    query = select(Persona)
    
    # Get total count
    count_query = select(func.count()).select_from(Persona)
    total = await db.scalar(count_query)
    
    # Get paginated results
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    personas = result.scalars().all()
    
    return PersonaList(
        data=[PersonaResponse.model_validate(p) for p in personas],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total
    )


@router.post("", response_model=PersonaResponse)
async def create_persona(
    persona: PersonaCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new persona."""
    # Check if name exists
    existing = await db.execute(
        select(Persona).where(Persona.name == persona.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Persona name already exists")
    
    db_persona = Persona(
        **persona.model_dump(),
        updated_at=datetime.utcnow()
    )
    db.add(db_persona)
    await db.commit()
    await db.refresh(db_persona)
    
    return PersonaResponse.model_validate(db_persona)


@router.get("/{persona_id}", response_model=PersonaResponse)
async def get_persona(
    persona_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get persona details."""
    import uuid
    try:
        persona_uuid = _parse_uuid(persona_id)
        persona = await db.get(Persona, persona_uuid)
    except ValueError:
        # Try to find by name
        result = await db.execute(
            select(Persona).where(Persona.name == persona_id)
        )
        persona = result.scalar_one_or_none()
    
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    
    return PersonaResponse.model_validate(persona)


@router.patch("/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    persona_id: str,
    update: PersonaUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a persona."""
    import uuid
    persona_uuid = _parse_uuid(persona_id)
    persona = await db.get(Persona, persona_uuid)
    
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    
    # Update fields
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(persona, field, value)
    
    persona.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(persona)
    
    return PersonaResponse.model_validate(persona)


@router.delete("/{persona_id}")
async def delete_persona(
    persona_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a persona."""
    import uuid
    persona_uuid = _parse_uuid(persona_id)
    persona = await db.get(Persona, persona_uuid)
    
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    
    await db.delete(persona)
    await db.commit()
    
    return {"status": "deleted"}