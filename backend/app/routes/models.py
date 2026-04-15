"""Model CRUD endpoints."""

import uuid
from datetime import datetime
from urllib.parse import urlparse
import socket
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Model, Provider
from app.schemas.model import ModelCreate, ModelUpdate, ModelResponse, ModelList
from app.middleware.auth import verify_api_key
from app.services.provider_credentials import has_provider_api_key
from app.routes.model_validate import validate_model_config
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/models", tags=["models"], dependencies=[Depends(verify_api_key)])

_LOCAL_MODEL_PROVIDERS = {"ollama", "local", "lm-studio", "lmstudio", "llamacpp"}


def _apply_validation_result(model: Model, validation: dict) -> str:
    if validation.get("live_verified"):
        model.validation_status = "validated"
        model.validated_at = datetime.utcnow()
        model.validation_source = validation.get("source")
        model.validation_warning = validation.get("warning")
        model.validation_error = None
        model.is_active = True
        return "validated"

    if validation.get("valid"):
        model.validation_status = model.validation_status or "unverified"
        model.validation_source = validation.get("source")
        model.validation_warning = validation.get("warning")
        model.validation_error = None
        return "review"

    model.validation_status = "failed"
    model.validation_source = validation.get("source")
    model.validation_warning = validation.get("warning")
    model.validation_error = validation.get("warning") or f"Live validation failed for {model.model_id}"
    if model.is_active:
        model.is_active = False
    return "failed"


def _can_connect_to_base_url(base_url: str | None, timeout: float = 0.35) -> bool:
    if not base_url:
        return False
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not host:
            return False
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _provider_is_usable(provider_name: str | None, provider_base_url: str | None = None) -> bool:
    normalized = (provider_name or "").lower().strip()
    if normalized in _LOCAL_MODEL_PROVIDERS:
        return _can_connect_to_base_url(provider_base_url)
    return has_provider_api_key(normalized)


@router.get("", response_model=ModelList)
async def list_models(
    limit: int = 50,
    offset: int = 0,
    provider_id: str = None,
    active_only: bool = False,
    usable_only: bool = False,
    validated_only: bool = False,
    chat_only: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """List all models with optional filtering."""
    # Join with provider to get provider name
    query = select(
        Model,
        Provider.name.label('provider_name'),
        Provider.is_active.label('provider_active'),
        Provider.api_base_url.label('provider_api_base_url'),
    ).join(
        Provider, Model.provider_id == Provider.id, isouter=True
    )
    
    if provider_id:
        query = query.where(Model.provider_id == uuid.UUID(provider_id))

    query = query.order_by(Provider.name, Model.display_name, Model.model_id)
    result = await db.execute(query)
    
    models = []
    for row in result:
        model = row[0]
        provider_name = row[1]
        provider_active = row[2]
        provider_api_base_url = row[3]
        capabilities = model.capabilities or {}

        if active_only and (not model.is_active or provider_active is False):
            continue
        if usable_only and not _provider_is_usable(provider_name, provider_api_base_url):
            continue
        if validated_only and (model.validation_status or "unverified") != "validated":
            continue
        if chat_only and (capabilities.get("chat") is False or capabilities.get("image_generation")):
            continue

        model_dict = {
            "id": model.id,
            "model_id": model.model_id,
            "display_name": model.display_name,
            "provider_id": model.provider_id,
            "provider_name": provider_name,
            "cost_per_1m_input": model.cost_per_1m_input,
            "cost_per_1m_output": model.cost_per_1m_output,
            "context_window": model.context_window,
            "capabilities": capabilities,
            "is_active": model.is_active,
            "validation_status": model.validation_status or "unverified",
            "validated_at": model.validated_at,
            "validation_source": model.validation_source,
            "validation_warning": model.validation_warning,
            "validation_error": model.validation_error,
            "created_at": model.created_at,
        }
        models.append(model_dict)

    total = len(models)
    paged_models = models[offset:offset + limit]
    return ModelList(
        data=paged_models,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(paged_models) < total,
    )


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
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    validation = await validate_model_config(model.model_id, provider.name)
    if not validation.get("live_verified"):
        raise HTTPException(
            status_code=400,
            detail=validation.get("warning")
            or f"Model '{model.model_id}' has not been successfully live-validated for provider '{provider.name}'.",
        )
    
    new_model = Model(
        id=uuid.uuid4(),
        provider_id=model.provider_id,
        model_id=model.model_id,
        display_name=model.display_name,
        cost_per_1m_input=model.cost_per_1m_input,
        cost_per_1m_output=model.cost_per_1m_output,
        context_window=model.context_window,
        capabilities=model.capabilities or {},
        is_active=model.is_active if model.is_active is not None else True,
        validation_status="validated",
        validated_at=datetime.utcnow(),
        validation_source=validation.get("source"),
        validation_warning=validation.get("warning"),
        validation_error=None,
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
    
    if updates.model_id is not None:
        provider_result = await db.execute(select(Provider).where(Provider.id == model.provider_id))
        provider = provider_result.scalar_one_or_none()
        provider_name = provider.name if provider else ""
        validation = await validate_model_config(updates.model_id, provider_name)
        if not validation.get("live_verified"):
            raise HTTPException(
                status_code=400,
                detail=validation.get("warning")
                or f"Model '{updates.model_id}' has not been successfully live-validated for provider '{provider_name}'.",
            )
        model.model_id = updates.model_id
        model.validation_status = "validated"
        model.validated_at = datetime.utcnow()
        model.validation_source = validation.get("source")
        model.validation_warning = validation.get("warning")
        model.validation_error = None
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
        if updates.is_active and (model.validation_status or "unverified") != "validated":
            raise HTTPException(status_code=400, detail="Only live-validated models can be activated.")
        model.is_active = updates.is_active
    
    await db.commit()
    await db.refresh(model)
    return model


@router.post("/{model_id}/revalidate", response_model=ModelResponse)
async def revalidate_model(
    model_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Re-run live validation for an existing model and persist the result."""
    try:
        model_uuid = uuid.UUID(model_id)
        result = await db.execute(select(Model).where(Model.id == model_uuid))
        model = result.scalar_one_or_none()
    except ValueError:
        result = await db.execute(select(Model).where(Model.model_id == model_id))
        model = result.scalars().first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    provider_result = await db.execute(select(Provider).where(Provider.id == model.provider_id))
    provider = provider_result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    validation = await validate_model_config(model.model_id, provider.name)
    _apply_validation_result(model, validation)

    await db.commit()
    await db.refresh(model)
    return model


@router.post("/validate-catalog")
async def validate_catalog(
    provider_id: str | None = None,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """Bulk-validate the current catalog and separate validated from review/failed rows."""
    query = select(Model).order_by(Model.created_at)
    if provider_id:
        query = query.where(Model.provider_id == uuid.UUID(provider_id))
    if active_only:
        query = query.where(Model.is_active == True)

    result = await db.execute(query)
    models = list(result.scalars().all())

    provider_cache: dict[str, Provider | None] = {}
    grouped_models: dict[str, list[Model]] = {}
    summary = {
        "validated": 0,
        "needs_review": 0,
        "failed": 0,
        "processed": 0,
        "providers": {},
    }

    for model in models:
        grouped_models.setdefault(str(model.provider_id), []).append(model)
        provider_key = str(model.provider_id)
        provider = provider_cache.get(provider_key)
        if provider_key not in provider_cache:
            provider_result = await db.execute(select(Provider).where(Provider.id == model.provider_id))
            provider = provider_result.scalar_one_or_none()
            provider_cache[provider_key] = provider

    from app.routes.model_sync import discover_provider_models, fetch_ollama_models, get_catalog_model_viability

    for provider_key, provider_models in grouped_models.items():
        provider = provider_cache.get(provider_key)
        provider_name = provider.name if provider else "unknown"
        provider_summary = summary["providers"].setdefault(provider_name, {
            "validated": 0,
            "needs_review": 0,
            "failed": 0,
            "processed": 0,
        })

        if not provider or provider.is_active is False:
            for model in provider_models:
                model.validation_status = "failed"
                model.validation_source = "provider_inactive"
                model.validation_warning = "Provider is inactive or unavailable."
                model.validation_error = "provider_inactive"
                model.is_active = False
                summary["failed"] += 1
                summary["processed"] += 1
                provider_summary["failed"] += 1
                provider_summary["processed"] += 1
            continue

        catalog_models_by_id: dict[str, dict] | None = None
        catalog_source: str | None = None
        catalog_error: str | None = None

        try:
            if provider_name in _LOCAL_MODEL_PROVIDERS:
                ollama_models = await fetch_ollama_models(provider.api_base_url or "http://localhost:11434")
                catalog_models_by_id = {m.get("name"): m for m in ollama_models if m.get("name")}
                catalog_source = "ollama_catalog"
            else:
                discovered_models, discovered_source = await discover_provider_models(provider_name)
                if discovered_source in {"provider_api", "codex_proxy"}:
                    catalog_models_by_id = {
                        m.get("model_id"): m
                        for m in discovered_models
                        if m.get("model_id")
                    }
                    catalog_source = discovered_source
                else:
                    catalog_error = f"Could not validate against a live {provider_name} catalog."
        except Exception as exc:
            catalog_error = f"Could not validate against a live {provider_name} catalog — {type(exc).__name__}."

        for model in provider_models:
            if catalog_models_by_id is not None:
                catalog_model = catalog_models_by_id.get(model.model_id)
                if catalog_model is not None:
                    is_viable, viability_warning, _ = get_catalog_model_viability(catalog_model)
                    if is_viable:
                        validation = {
                            "valid": True,
                            "live_verified": True,
                            "source": "catalog_probe",
                            "warning": None,
                        }
                    else:
                        validation = {
                            "valid": False,
                            "live_verified": False,
                            "source": f"catalog_probe:{catalog_source}",
                            "warning": viability_warning,
                        }
                else:
                    validation = {
                        "valid": False,
                        "live_verified": False,
                        "source": f"catalog_probe:{catalog_source}",
                        "warning": f"This model is not exposed by the live {provider_name} catalog.",
                    }
            else:
                validation = {
                    "valid": True,
                    "live_verified": False,
                    "source": "catalog_probe_unavailable",
                    "warning": catalog_error,
                }

            outcome = _apply_validation_result(model, validation)
            summary[outcome if outcome != "review" else "needs_review"] += 1
            summary["processed"] += 1
            provider_summary[outcome if outcome != "review" else "needs_review"] += 1
            provider_summary["processed"] += 1

    await db.commit()
    return {
        "ok": True,
        "message": f"Validated {summary['processed']} catalog models.",
        **summary,
    }


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
