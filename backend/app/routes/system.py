"""Self-healing and recovery endpoints."""

import os
import sys
import signal
import asyncio
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from app.middleware.auth import verify_api_key
from app.services.self_healing import self_healing
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/system", tags=["system"], dependencies=[Depends(verify_api_key)])

# Track startup time for uptime calculation
_START_TIME = time.time()


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


@router.get("/info")
async def server_info():
    """Return server uptime, Python version, and process info."""
    uptime_seconds = int(time.time() - _START_TIME)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"

    return {
        "status": "running",
        "pid": os.getpid(),
        "python_version": sys.version.split()[0],
        "uptime_seconds": uptime_seconds,
        "uptime": uptime_str,
        "started_at": datetime.fromtimestamp(_START_TIME, tz=timezone.utc).isoformat(),
    }


@router.post("/restart")
async def restart_server():
    """
    Gracefully restart the backend worker process.
    Sends SIGTERM to the current process — uvicorn --reload will
    automatically spawn a fresh worker.
    """
    logger.info("Restart requested via API — sending SIGTERM to worker process")

    async def _do_restart():
        await asyncio.sleep(0.3)  # Let the HTTP response go out first
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.create_task(_do_restart())

    return JSONResponse({"status": "restarting", "message": "Worker is restarting — ready again in a few seconds."})