"""Model routing policy and preview endpoints."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_role, verify_api_key
from app.services.model_routing import get_routing_policy, preview_route, set_routing_policy


router = APIRouter(prefix="/v1/routing", tags=["routing"], dependencies=[Depends(verify_api_key)])


class RoutingPreviewRequest(BaseModel):
    task_type: str = "chat"
    prompt_preview: str = ""
    risk_level: str = "normal"
    budget_mode: str = "balanced"
    latency_priority: str = "balanced"
    preferred_provider: Optional[str] = None


class RoutingPolicyUpdate(BaseModel):
    policy: dict[str, Any] = Field(default_factory=dict)


@router.post("/preview")
async def preview_model_route(body: RoutingPreviewRequest, db: AsyncSession = Depends(get_db)):
    return await preview_route(
        db,
        task_type=body.task_type,
        prompt_preview=body.prompt_preview,
        risk_level=body.risk_level,
        budget_mode=body.budget_mode,
        latency_priority=body.latency_priority,
        preferred_provider=body.preferred_provider,
    )


@router.get("/policy")
async def get_model_routing_policy(db: AsyncSession = Depends(get_db)):
    return {"policy": await get_routing_policy(db)}


@router.put("/policy", dependencies=[Depends(require_role("owner", "admin"))])
async def put_model_routing_policy(body: RoutingPolicyUpdate, db: AsyncSession = Depends(get_db)):
    if not isinstance(body.policy, dict) or not body.policy:
        raise HTTPException(status_code=422, detail="policy must be a non-empty object")
    policy = await set_routing_policy(db, body.policy)
    return {"policy": policy}
