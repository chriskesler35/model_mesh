"""Remote access and session management endpoints."""

import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/remote", tags=["remote"])


# Session storage (in-memory for now, could be database-backed)
sessions: Dict[str, Dict[str, Any]] = {}


class SessionCreate(BaseModel):
    """Create a new agent session."""
    agent_type: str
    task: str
    model: Optional[str] = None
    max_iterations: Optional[int] = 10
    callback_url: Optional[str] = None  # Telegram/Slack webhook for notifications


class SessionStatus(BaseModel):
    """Session status response."""
    session_id: str
    agent_type: str
    task: str
    status: str  # pending, running, completed, failed, cancelled
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None


class HealthCheck(BaseModel):
    """Health check response."""
    status: str
    version: str
    uptime_seconds: int
    models_count: int
    personas_count: int
    agents_count: int
    sessions_active: int
    system: Dict[str, Any]


START_TIME = datetime.now()


@router.get("/health", response_model=HealthCheck)
async def health_check():
    """Get system health status for remote monitoring."""
    from app.database import AsyncSessionLocal
    from app.models import Model, Persona
    from app.models.agent import Agent
    from app.routes.agents import DEFAULT_AGENTS
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    
    # Get counts
    async with AsyncSessionLocal() as db:
        models_result = await db.execute(select(Model).where(Model.is_active == True))
        models_count = len(models_result.scalars().all())
        
        personas_result = await db.execute(select(Persona))
        personas_count = len(personas_result.scalars().all())
    
    # Default agents count
    agents_count = len(DEFAULT_AGENTS)
    
    # Active sessions
    active_sessions = len([s for s in sessions.values() if s["status"] == "running"])
    
    # System info
    import psutil
    system_info = {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:\\').percent,
        "python_version": os.sys.version,
    }
    
    return HealthCheck(
        status="healthy",
        version="0.2.0",
        uptime_seconds=int((datetime.now() - START_TIME).total_seconds()),
        models_count=models_count,
        personas_count=personas_count,
        agents_count=agents_count,
        sessions_active=active_sessions,
        system=system_info
    )


@router.post("/sessions", response_model=SessionStatus)
async def create_session(
    session: SessionCreate,
    background_tasks: BackgroundTasks
):
    """Create a new agent session."""
    import uuid
    
    session_id = str(uuid.uuid4())
    
    sessions[session_id] = {
        "session_id": session_id,
        "agent_type": session.agent_type,
        "task": session.task,
        "model": session.model,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "progress": {},
        "callback_url": session.callback_url,
        "max_iterations": session.max_iterations
    }
    
    # Start session in background
    background_tasks.add_task(run_session, session_id)
    
    return SessionStatus(**sessions[session_id])


@router.get("/sessions", response_model=List[SessionStatus])
async def list_sessions(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    """List all sessions, optionally filtered by status."""
    filtered = list(sessions.values())
    
    if status:
        filtered = [s for s in filtered if s["status"] == status]
    
    # Sort by created_at descending
    filtered.sort(key=lambda x: x["created_at"], reverse=True)
    
    return [SessionStatus(**s) for s in filtered[offset:offset + limit]]


@router.get("/sessions/{session_id}", response_model=SessionStatus)
async def get_session(session_id: str):
    """Get status of a specific session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionStatus(**sessions[session_id])


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(session_id: str):
    """Cancel a running session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    if session["status"] not in ["pending", "running"]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel session with status {session['status']}")
    
    session["status"] = "cancelled"
    session["completed_at"] = datetime.now().isoformat()
    
    return {"status": "cancelled", "session_id": session_id}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session record."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    if session["status"] == "running":
        raise HTTPException(status_code=400, detail="Cannot delete running session. Cancel first.")
    
    del sessions[session_id]
    
    return {"status": "deleted", "session_id": session_id}


async def run_session(session_id: str):
    """Run an agent session in the background."""
    session = sessions[session_id]
    
    try:
        session["status"] = "running"
        session["started_at"] = datetime.now().isoformat()
        
        # This is a placeholder for actual agent execution
        # In a real implementation, this would:
        # 1. Load the agent configuration
        # 2. Initialize the agent with the task
        # 3. Run the agent loop
        # 4. Stream progress updates
        # 5. Handle completion/failure
        
        # Simulate some work
        await asyncio.sleep(2)
        
        session["progress"] = {"step": 1, "total": 3, "message": "Analyzing task..."}
        await asyncio.sleep(2)
        
        session["progress"] = {"step": 2, "total": 3, "message": "Executing..."}
        await asyncio.sleep(2)
        
        session["progress"] = {"step": 3, "total": 3, "message": "Finalizing..."}
        await asyncio.sleep(1)
        
        # Mark as completed
        session["status"] = "completed"
        session["completed_at"] = datetime.now().isoformat()
        session["result"] = f"Task '{session['task']}' completed by {session['agent_type']} agent"
        
        # Send callback if configured
        if session.get("callback_url"):
            await send_callback(session["callback_url"], session)
            
    except Exception as e:
        logger.error(f"Session {session_id} failed: {e}")
        session["status"] = "failed"
        session["error"] = str(e)
        session["completed_at"] = datetime.now().isoformat()
        
        if session.get("callback_url"):
            await send_callback(session["callback_url"], session)


async def send_callback(url: str, data: Dict[str, Any]):
    """Send a callback to Telegram/Slack webhook."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=data)
    except Exception as e:
        logger.error(f"Callback failed: {e}")


@router.get("/tailscale-info")
async def get_tailscale_info():
    """Get Tailscale connection info for remote access."""
    import socket
    
    hostname = socket.gethostname()
    
    # Try to get Tailscale IP
    tailscale_ip = None
    try:
        # Check for Tailscale interface
        import subprocess
        result = subprocess.run(
            ["tailscale", "ip"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            ips = result.stdout.strip().split('\n')
            # IPv4 is usually first
            tailscale_ip = ips[0] if ips else None
    except Exception:
        pass
    
    return {
        "hostname": hostname,
        "tailscale_ip": tailscale_ip,
        "backend_port": 19000,
        "frontend_port": 3000,
        "api_url": f"http://{tailscale_ip or hostname}:19000",
        "frontend_url": f"http://{tailscale_ip or hostname}:3000",
        "instructions": {
            "tailscale": f"Connect via Tailscale: http://{tailscale_ip or '100.106.217.99'}:3000",
            "local": f"Local access: http://localhost:3000"
        }
    }