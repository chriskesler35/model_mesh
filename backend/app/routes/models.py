"""Model endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import Model, Provider
from app.schemas import ModelCreate, ModelUpdate, ModelResponse, ModelList
from app.middleware.auth import verify_api_key

router = APIRouter(prefix="/v1/models", tags=["models"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=ModelList)
async def list_models(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    provider_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all available models."""
    query = select(Model)
    
    if provider_id:
        query = query.where(Model.provider_id == provider_id)
    if is_active is not None:
        query = query.where(Model.is_active == is_active)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Get paginated results
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    models = result.scalars().all()
    
    # Get provider names
    model_responses = []
    for m in models:
        provider = await db.get(Provider, m.provider_id)
        model_responses.append(ModelResponse(
            **{k: v for k, v in m.__dict__.items() if not k.startswith('_')},
            provider_name=provider.name if provider else None
        ))
    
    return ModelList(
        data=model_responses,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total
    )


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get model details."""
    import uuid
    try:
        model_uuid = uuid.UUID(model_id)
        model = await db.get(Model, model_uuid)
    except ValueError:
        # Try to find by model_id string
        result = await db.execute(
            select(Model).where(Model.model_id == model_id)
        )
        model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    provider = await db.get(Provider, model.provider_id)
    
    return ModelResponse(
        **{k: v for k, v in model.__dict__.items() if not k.startswith('_')},
        provider_name=provider.name if provider else None
    )