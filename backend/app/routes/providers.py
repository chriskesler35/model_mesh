"""Provider endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Provider
from app.middleware.auth import verify_api_key

router = APIRouter(prefix="/v1/providers", tags=["providers"], dependencies=[Depends(verify_api_key)])


@router.get("")
async def list_providers(db: AsyncSession = Depends(get_db)):
    """List all providers."""
    result = await db.execute(select(Provider))
    providers = result.scalars().all()
    
    return {
        "data": [
            {
                "id": str(p.id),
                "name": p.name,
                "display_name": p.display_name,
                "is_active": p.is_active
            }
            for p in providers
        ],
        "total": len(providers)
    }