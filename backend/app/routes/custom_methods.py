"""CRUD endpoints for user-created custom methods.

Custom methods let users define their own development methodologies
with custom phases, alongside built-in methods (BMAD, GSD, SuperPowers).
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import verify_api_key
from app.models.custom_method import CustomMethod

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/methods/custom",
    tags=["custom-methods"],
    dependencies=[Depends(verify_api_key)],
)


# ─── Request / Response schemas ──────────────────────────────────────────────

class PhaseSchema(BaseModel):
    """Schema for a single phase in a custom method."""
    name: str = Field(..., min_length=1, description="Phase name (e.g. 'Analyst', 'Coder')")
    role: str = Field(..., min_length=1, description="Agent role (e.g. 'Business Analyst')")
    default_model: Optional[str] = None
    system_prompt: Optional[str] = None
    artifact_type: Optional[str] = Field(None, description="Output type: json, md, or code")
    depends_on: Optional[List[str]] = None


class CustomMethodCreate(BaseModel):
    """Request body for creating a custom method."""
    name: str = Field(..., min_length=1, max_length=200, description="Unique method name")
    description: Optional[str] = None
    phases: List[PhaseSchema] = Field(..., min_length=1, description="Ordered list of phases")
    trigger_keywords: Optional[List[str]] = None


class CustomMethodUpdate(BaseModel):
    """Request body for updating a custom method."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    phases: Optional[List[PhaseSchema]] = Field(None, min_length=1)
    trigger_keywords: Optional[List[str]] = None
    is_active: Optional[bool] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _validate_phases(phases: List[PhaseSchema]) -> List[dict]:
    """Validate and convert phase schemas to dicts for storage."""
    result = []
    seen_names = set()
    for phase in phases:
        if phase.name in seen_names:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate phase name: '{phase.name}'"
            )
        seen_names.add(phase.name)

        # Validate depends_on references
        if phase.depends_on:
            for dep in phase.depends_on:
                if dep not in seen_names:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Phase '{phase.name}' depends on unknown phase '{dep}'"
                    )

        # Validate artifact_type if provided
        valid_artifact_types = {"json", "md", "code"}
        if phase.artifact_type and phase.artifact_type not in valid_artifact_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid artifact_type '{phase.artifact_type}' for phase '{phase.name}'. Must be one of: {', '.join(valid_artifact_types)}"
            )

        result.append(phase.model_dump(exclude_none=True))
    return result


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_custom_method(
    body: CustomMethodCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new custom method."""
    # Check for duplicate name
    existing = await db.execute(
        select(CustomMethod).where(CustomMethod.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"A method named '{body.name}' already exists"
        )

    validated_phases = _validate_phases(body.phases)

    method = CustomMethod(
        name=body.name,
        description=body.description,
        phases=validated_phases,
        trigger_keywords=body.trigger_keywords,
    )
    db.add(method)
    await db.commit()
    await db.refresh(method)

    logger.info(f"Created custom method '{method.name}' with {len(validated_phases)} phases")
    return method.to_dict()


@router.get("")
async def list_custom_methods(
    db: AsyncSession = Depends(get_db),
):
    """List all custom methods."""
    result = await db.execute(
        select(CustomMethod).order_by(CustomMethod.created_at)
    )
    methods = result.scalars().all()
    return {"data": [m.to_dict() for m in methods]}


@router.get("/{method_id}")
async def get_custom_method(
    method_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single custom method by ID."""
    result = await db.execute(
        select(CustomMethod).where(CustomMethod.id == method_id)
    )
    method = result.scalar_one_or_none()
    if not method:
        raise HTTPException(status_code=404, detail="Custom method not found")
    return method.to_dict()


@router.put("/{method_id}")
async def update_custom_method(
    method_id: str,
    body: CustomMethodUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a custom method."""
    result = await db.execute(
        select(CustomMethod).where(CustomMethod.id == method_id)
    )
    method = result.scalar_one_or_none()
    if not method:
        raise HTTPException(status_code=404, detail="Custom method not found")

    # Check name uniqueness if name is being changed
    if body.name is not None and body.name != method.name:
        dup = await db.execute(
            select(CustomMethod).where(CustomMethod.name == body.name)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"A method named '{body.name}' already exists"
            )
        method.name = body.name

    if body.description is not None:
        method.description = body.description

    if body.phases is not None:
        method.phases = _validate_phases(body.phases)

    if body.trigger_keywords is not None:
        method.trigger_keywords = body.trigger_keywords

    if body.is_active is not None:
        method.is_active = body.is_active

    await db.commit()
    await db.refresh(method)

    logger.info(f"Updated custom method '{method.name}' (id={method_id})")
    return method.to_dict()


@router.delete("/{method_id}")
async def delete_custom_method(
    method_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a custom method."""
    result = await db.execute(
        select(CustomMethod).where(CustomMethod.id == method_id)
    )
    method = result.scalar_one_or_none()
    if not method:
        raise HTTPException(status_code=404, detail="Custom method not found")

    name = method.name
    await db.delete(method)
    await db.commit()

    logger.info(f"Deleted custom method '{name}' (id={method_id})")
    return {"ok": True, "deleted": method_id}
