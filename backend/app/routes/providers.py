"""Provider endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from app.database import get_db
from app.models import Provider
from app.models.model import Model
from app.middleware.auth import verify_api_key

router = APIRouter(prefix="/v1/providers", tags=["providers"], dependencies=[Depends(verify_api_key)])


@router.get("")
async def list_providers(active_only: bool = True, db: AsyncSession = Depends(get_db)):
    """List all providers."""
    query = select(Provider)
    if active_only:
        query = query.where(Provider.is_active == True)

    result = await db.execute(query.order_by(Provider.display_name, Provider.name))
    providers = result.scalars().all()

    model_counts_result = await db.execute(
        select(
            Model.provider_id,
            func.count(Model.id).label("model_count"),
            func.sum(case((Model.is_active == True, 1), else_=0)).label("active_model_count"),
        ).group_by(Model.provider_id)
    )
    model_counts = {
        str(provider_id): {
            "model_count": int(model_count or 0),
            "active_model_count": int(active_model_count or 0),
        }
        for provider_id, model_count, active_model_count in model_counts_result.all()
    }
    
    return {
        "data": [
            {
                "id": str(p.id),
                "name": p.name,
                "display_name": p.display_name,
                "is_active": p.is_active,
                "model_count": model_counts.get(str(p.id), {}).get("model_count", 0),
                "active_model_count": model_counts.get(str(p.id), {}).get("active_model_count", 0),
            }
            for p in providers
        ],
        "total": len(providers)
    }