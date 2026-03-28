"""Model CRUD endpoints."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Model, Provider
from app.schemas.model import ModelCreate, ModelUpdate, ModelResponse, ModelList
from app.middleware.auth import verify_api_key
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/models", tags=["models"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=ModelList)
async def list_models(
    limit: int = 50,
    offset: int = 0,
    provider_id: str = None,
    db: AsyncSession = Depends(get_db)
):
    """List all models with optional filtering."""
    # Join with provider to get provider name
    query = select(Model, Provider.name.label('provider_name')).join(
        Provider, Model.provider_id == Provider.id, isouter=True
    )
    
    if provider_id:
        query = query.where(Model.provider_id == uuid.UUID(provider_id))
    
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    
    models = []
    for row in result:
        model = row[0]
        provider_name = row[1]
        model_dict = {
            "id": model.id,
            "model_id": model.model_id,
            "display_name": model.display_name,
            "provider_id": model.provider_id,
            "provider_name": provider_name,
            "cost_per_1m_input": model.cost_per_1m_input,
            "cost_per_1m_output": model.cost_per_1m_output,
            "context_window": model.context_window,
            "capabilities": model.capabilities,
            "is_active": model.is_active,
            "created_at": model.created_at,
        }
        models.append(model_dict)
    
    # Get total count
    count_query = select(Model)
    if provider_id:
        count_query = count_query.where(Model.provider_id == uuid.UUID(provider_id))
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return ModelList(data=models, total=total, limit=limit, offset=offset, has_more=offset + len(models) < total)


@router.post("", response_model=ModelResponse)
async def create_model(
    model: ModelCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new model."""
    # Verify provider exists
    result = await db.execute(
        select(Provider).where(Provider.id == model.provider_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Provider not found")
    
    new_model = Model(
        id=uuid.uuid4(),
        provider_id=model.provider_id,
        model_id=model.model_id,
        display_name=model.display_name,
        cost_per_1m_input=model.cost_per_1m_input,
        cost_per_1m_output=model.cost_per_1m_output,
        context_window=model.context_window,
        capabilities=model.capabilities or {},
        is_active=model.is_active if model.is_active is not None else True
    )
    db.add(new_model)
    await db.commit()
    await db.refresh(new_model)
    return new_model


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a model by ID."""
    try:
        model_uuid = uuid.UUID(model_id)
        result = await db.execute(select(Model).where(Model.id == model_uuid))
    except ValueError:
        # Try by model_id string
        result = await db.execute(select(Model).where(Model.model_id == model_id))
    
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    return model


@router.patch("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: str,
    updates: ModelUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a model."""
    try:
        model_uuid = uuid.UUID(model_id)
        result = await db.execute(select(Model).where(Model.id == model_uuid))
    except ValueError:
        result = await db.execute(select(Model).where(Model.model_id == model_id))
    
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    if updates.display_name is not None:
        model.display_name = updates.display_name
    if updates.cost_per_1m_input is not None:
        model.cost_per_1m_input = updates.cost_per_1m_input
    if updates.cost_per_1m_output is not None:
        model.cost_per_1m_output = updates.cost_per_1m_output
    if updates.context_window is not None:
        model.context_window = updates.context_window
    if updates.capabilities is not None:
        model.capabilities = updates.capabilities
    if updates.is_active is not None:
        model.is_active = updates.is_active
    
    await db.commit()
    await db.refresh(model)
    return model


@router.delete("/{model_id}")
async def delete_model(
    model_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a model and update any personas using it."""
    from app.models import Persona
    
    try:
        model_uuid = uuid.UUID(model_id)
        result = await db.execute(select(Model).where(Model.id == model_uuid))
    except ValueError:
        result = await db.execute(select(Model).where(Model.model_id == model_id))
    
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Find all personas using this model as primary or fallback
    personas_result = await db.execute(
        select(Persona).where(
            (Persona.primary_model_id == model.id) | 
            (Persona.fallback_model_id == model.id)
        )
    )
    affected_personas = personas_result.scalars().all()
    
    updated_personas = []
    
    for persona in affected_personas:
        # If this is the primary model, swap to fallback
        if persona.primary_model_id == model.id:
            if persona.fallback_model_id and persona.fallback_model_id != model.id:
                # Swap primary to fallback
                persona.primary_model_id = persona.fallback_model_id
                persona.fallback_model_id = None
            else:
                # Find first available model
                all_models_result = await db.execute(
                    select(Model).where(
                        (Model.is_active == True) & 
                        (Model.id != model.id)
                    ).limit(1)
                )
                first_available = all_models_result.scalar_one_or_none()
                if first_available:
                    persona.primary_model_id = first_available.id
                    persona.fallback_model_id = None
                else:
                    # No other models available - mark persona as unusable
                    persona.primary_model_id = None
                    persona.fallback_model_id = None
            
            updated_personas.append({
                "id": str(persona.id),
                "name": persona.name,
                "action": "primary_model_replaced"
            })
        
        # If this is the fallback model, just clear it
        elif persona.fallback_model_id == model.id:
            persona.fallback_model_id = None
            updated_personas.append({
                "id": str(persona.id),
                "name": persona.name,
                "action": "fallback_model_cleared"
            })
    
    # Delete the model
    await db.delete(model)
    await db.commit()
    
    return {
        "status": "deleted",
        "affected_personas": updated_personas
    }


@router.get("/provider/{provider_name}", response_model=ModelList)
async def list_models_by_provider(
    provider_name: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """List models by provider name."""
    result = await db.execute(
        select(Provider).where(Provider.name == provider_name.lower())
    )
    provider = result.scalar_one_or_none()
    
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    result = await db.execute(
        select(Model)
        .where(Model.provider_id == provider.id)
        .limit(limit)
        .offset(offset)
    )
    models = result.scalars().all()
    
    return ModelList(data=models, total=len(models), limit=limit, offset=offset, has_more=False)