"""CRUD endpoints for user-saved custom workflows."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import verify_api_key
from app.models.custom_workflow import CustomWorkflow

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/workflows/custom",
    tags=["custom-workflows"],
    dependencies=[Depends(verify_api_key)],
)


# ─── Schemas ─────────────────────────────────────────────────────────────────

class CustomWorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    graph_data: dict = Field(..., description="Serialized graph: {nodes, edges}")


class CustomWorkflowUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    graph_data: Optional[dict] = None


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("")
async def list_custom_workflows(db: AsyncSession = Depends(get_db)):
    """List all saved custom workflows."""
    result = await db.execute(
        select(CustomWorkflow).order_by(CustomWorkflow.updated_at.desc())
    )
    workflows = result.scalars().all()
    return [w.to_dict() for w in workflows]


@router.get("/{workflow_id}")
async def get_custom_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single custom workflow by ID."""
    result = await db.execute(
        select(CustomWorkflow).where(CustomWorkflow.id == workflow_id)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf.to_dict()


@router.post("", status_code=201)
async def create_custom_workflow(
    body: CustomWorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new custom workflow."""
    wf = CustomWorkflow(
        name=body.name,
        description=body.description,
        graph_data=body.graph_data,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    logger.info(f"Created custom workflow '{wf.name}' ({wf.id})")
    return wf.to_dict()


@router.put("/{workflow_id}")
async def update_custom_workflow(
    workflow_id: str,
    body: CustomWorkflowUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing custom workflow."""
    result = await db.execute(
        select(CustomWorkflow).where(CustomWorkflow.id == workflow_id)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if body.name is not None:
        wf.name = body.name
    if body.description is not None:
        wf.description = body.description
    if body.graph_data is not None:
        wf.graph_data = body.graph_data

    await db.commit()
    await db.refresh(wf)
    logger.info(f"Updated custom workflow '{wf.name}' ({wf.id})")
    return wf.to_dict()


@router.delete("/{workflow_id}", status_code=204)
async def delete_custom_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a custom workflow."""
    result = await db.execute(
        select(CustomWorkflow).where(CustomWorkflow.id == workflow_id)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    await db.delete(wf)
    await db.commit()
    logger.info(f"Deleted custom workflow '{wf.name}' ({workflow_id})")
