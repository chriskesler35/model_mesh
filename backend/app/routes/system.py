"""Self-healing and recovery endpoints."""

from fastapi import APIRouter, Depends
from app.middleware.auth import verify_api_key
from app.services.self_healing import self_healing
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/system", tags=["system"], dependencies=[Depends(verify_api_key)])


@router.get("/health")
async def get_health():
    """Get comprehensive system health status."""
    return await self_healing.check_health()


@router.post("/snapshots")
async def create_snapshot(name: str = None):
    """Create a system snapshot for recovery point."""
    return await self_healing.create_snapshot(name)


@router.get("/snapshots")
async def list_snapshots():
    """List all available snapshots."""
    return {"snapshots": self_healing.list_snapshots()}


@router.post("/recover")
async def trigger_recovery():
    """Trigger automatic recovery from unhealthy state."""
    return await self_healing.recover()


@router.post("/rollback/{snapshot_name}")
async def rollback_to_snapshot(snapshot_name: str):
    """Rollback to a specific snapshot."""
    return await self_healing.restore_snapshot(snapshot_name)