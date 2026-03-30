"""Self-healing and recovery endpoints."""

import os
import sys
import asyncio
import time
from pathlib import Path
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


@router.get("/processes")
async def get_processes():
    """Get PM2 process status for all DevForgeAI services."""
    import subprocess
    try:
        result = subprocess.run(
            ["pm2", "jlist"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {"pm2": False, "processes": [], "error": "PM2 not running or not found"}

        import json as _json
        procs = _json.loads(result.stdout)
        # Filter to devforgeai processes only
        filtered = [
            {
                "name": p.get("name"),
                "status": p.get("pm2_env", {}).get("status"),
                "pid": p.get("pid"),
                "uptime": p.get("pm2_env", {}).get("pm_uptime"),
                "restarts": p.get("pm2_env", {}).get("restart_time", 0),
                "cpu": p.get("monit", {}).get("cpu"),
                "memory_mb": round(p.get("monit", {}).get("memory", 0) / 1024 / 1024, 1),
            }
            for p in procs
            if "devforgeai" in p.get("name", "")
        ]
        return {"pm2": True, "processes": filtered}
    except FileNotFoundError:
        return {"pm2": False, "processes": [], "error": "PM2 not installed"}
    except Exception as e:
        return {"pm2": False, "processes": [], "error": str(e)}


@router.get("/logs")
async def get_logs(lines: int = 50, service: str = "backend"):
    """Read recent log lines from PM2 log files."""
    log_dir = Path(__file__).parent.parent.parent.parent / "logs"
    log_file = log_dir / f"{service}-out.log"
    err_file = log_dir / f"{service}-error.log"

    out_lines, err_lines = [], []
    if log_file.exists():
        all_lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        out_lines = all_lines[-lines:]
    if err_file.exists():
        all_lines = err_file.read_text(encoding="utf-8", errors="replace").splitlines()
        err_lines = all_lines[-lines:]

    return {
        "service": service,
        "out": out_lines,
        "err": err_lines,
        "log_dir": str(log_dir),
    }


@router.post("/processes/{action}")
async def control_process(action: str, service: str = "all"):
    """Control PM2 processes: start, stop, restart."""
    import subprocess
    if action not in ("start", "stop", "restart"):
        raise HTTPException(status_code=400, detail="action must be start, stop, or restart")
    try:
        result = subprocess.run(
            ["pm2", action, service],
            capture_output=True, text=True, timeout=15
        )
        return {"ok": result.returncode == 0, "output": result.stdout + result.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    Trigger a graceful restart by touching app/main.py.
    uvicorn --reload watches for file changes and will automatically
    restart the worker — works reliably on Windows and Linux.
    """
    logger.info("Restart requested via API — touching main.py to trigger reload watcher")

    async def _do_restart():
        await asyncio.sleep(0.3)  # Let the HTTP response go out first
        # Touch main.py — the watchfiles reloader will detect the change
        # and restart the worker cleanly without killing the parent
        main_py = Path(__file__).parent.parent / "main.py"
        main_py.touch()

    asyncio.create_task(_do_restart())

    return JSONResponse({"status": "restarting", "message": "Reload triggered — server will be back in a few seconds."})