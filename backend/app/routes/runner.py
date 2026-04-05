"""Project Runner — execute user applications from within DevForgeAI.

Per-project subprocess manager with live SSE output streaming. One process
at a time per project — starting a new run kills the previous. User can
also explicitly stop via /stop.

Run commands are stored per-project in projects.json (run_command field),
with sensible auto-detection based on project files if unset.
"""

import asyncio
import json
import logging
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, AsyncGenerator, List

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/projects", tags=["runner"])

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_PROJECTS_FILE = _DATA_DIR / "projects.json"


# ─── Run state ────────────────────────────────────────────────────────────────
# Per-project: the running subprocess + its output queue + pending output buffer.
_processes: Dict[str, asyncio.subprocess.Process] = {}
_output_queues: Dict[str, asyncio.Queue] = {}
_output_buffers: Dict[str, List[dict]] = {}  # rolling log so late subscribers catch up
_run_metadata: Dict[str, dict] = {}  # {started_at, command, pid, exit_code, ...}

_MAX_BUFFER_LINES = 500


def _load_projects() -> dict:
    if _PROJECTS_FILE.exists():
        try:
            return json.loads(_PROJECTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_projects(projects: dict):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _PROJECTS_FILE.write_text(json.dumps(projects, indent=2), encoding="utf-8")


def _get_project(project_id: str) -> dict:
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return projects[project_id]


def _detect_run_command(project_path: Path) -> Optional[str]:
    """Guess a reasonable run command based on files in the project.

    Priority:
      1. package.json with 'dev' script → npm run dev
      2. package.json with 'start' script → npm start
      3. main.py → python main.py
      4. app.py → python app.py
      5. index.js / server.js → node <file>
      6. Cargo.toml → cargo run
      7. go.mod → go run .
    """
    if not project_path.exists():
        return None

    # Node
    pkg = project_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            if "dev" in scripts:
                return "npm run dev"
            if "start" in scripts:
                return "npm start"
        except Exception:
            pass

    # Python
    for name in ("main.py", "app.py", "run.py", "server.py"):
        if (project_path / name).exists():
            return f"python {name}"

    # Node entrypoints
    for name in ("index.js", "server.js", "app.js"):
        if (project_path / name).exists():
            return f"node {name}"

    # Rust
    if (project_path / "Cargo.toml").exists():
        return "cargo run"

    # Go
    if (project_path / "go.mod").exists():
        return "go run ."

    return None


def _resolve_python_exe(project: dict) -> Optional[str]:
    """Return path to the project's venv python if it exists, else None."""
    project_path = Path(project["path"])
    for candidate in (
        project_path / "venv" / "Scripts" / "python.exe",     # Windows venv
        project_path / ".venv" / "Scripts" / "python.exe",
        project_path / "venv" / "bin" / "python",             # Unix venv
        project_path / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _push_output(project_id: str, stream: str, text: str):
    """Write one output chunk to the rolling buffer + live queue."""
    evt = {
        "type": "output",
        "stream": stream,        # "stdout" | "stderr"
        "text": text,
        "ts": datetime.utcnow().isoformat(),
    }
    buf = _output_buffers.setdefault(project_id, [])
    buf.append(evt)
    if len(buf) > _MAX_BUFFER_LINES:
        del buf[0: len(buf) - _MAX_BUFFER_LINES]
    q = _output_queues.get(project_id)
    if q:
        try:
            q.put_nowait(evt)
        except asyncio.QueueFull:
            pass


def _push_meta(project_id: str, type: str, **payload):
    """Push a non-output event (started, exited, error, etc)."""
    evt = {"type": type, "ts": datetime.utcnow().isoformat(), **payload}
    buf = _output_buffers.setdefault(project_id, [])
    buf.append(evt)
    if len(buf) > _MAX_BUFFER_LINES:
        del buf[0: len(buf) - _MAX_BUFFER_LINES]
    q = _output_queues.get(project_id)
    if q:
        try:
            q.put_nowait(evt)
        except asyncio.QueueFull:
            pass


async def _stream_process_output(project_id: str, proc: asyncio.subprocess.Process):
    """Read stdout+stderr concurrently and push to queue, until process exits."""
    async def reader(pipe, stream_name):
        while True:
            line = await pipe.readline()
            if not line:
                break
            try:
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
            except Exception:
                text = repr(line)
            _push_output(project_id, stream_name, text)

    try:
        await asyncio.gather(
            reader(proc.stdout, "stdout"),
            reader(proc.stderr, "stderr"),
        )
        rc = await proc.wait()
        _push_meta(project_id, "exited", return_code=rc)
        if project_id in _run_metadata:
            _run_metadata[project_id]["exit_code"] = rc
            _run_metadata[project_id]["exited_at"] = datetime.utcnow().isoformat()
    except Exception as e:
        logger.error(f"Process output streaming failed for {project_id}: {e}")
        _push_meta(project_id, "error", message=str(e))
    finally:
        _processes.pop(project_id, None)


async def _kill_process(proc: asyncio.subprocess.Process, project_id: str):
    """Terminate a running subprocess gracefully, then force if needed."""
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    except Exception as e:
        logger.warning(f"Error killing process for {project_id}: {e}")


# ─── Schemas ──────────────────────────────────────────────────────────────────
class RunRequest(BaseModel):
    command: Optional[str] = None  # override; if None, uses project.run_command or auto-detect


class RunCommandUpdate(BaseModel):
    run_command: str


# ─── Routes ───────────────────────────────────────────────────────────────────
@router.get("/{project_id}/run/config", dependencies=[Depends(verify_api_key)])
async def get_run_config(project_id: str):
    """Return the project's current run command and auto-detection guess."""
    project = _get_project(project_id)
    saved = project.get("run_command") or ""
    detected = _detect_run_command(Path(project["path"]))
    venv_python = _resolve_python_exe(project)
    return {
        "run_command": saved,
        "detected_command": detected or "",
        "venv_python": venv_python,
        "effective_command": saved or detected or "",
    }


@router.put("/{project_id}/run/config", dependencies=[Depends(verify_api_key)])
async def set_run_config(project_id: str, body: RunCommandUpdate):
    """Save the run_command for a project."""
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    projects[project_id]["run_command"] = body.run_command.strip()
    projects[project_id]["updated_at"] = datetime.utcnow().isoformat()
    _save_projects(projects)
    return {"ok": True, "run_command": projects[project_id]["run_command"]}


@router.get("/{project_id}/run/status", dependencies=[Depends(verify_api_key)])
async def get_run_status(project_id: str):
    proc = _processes.get(project_id)
    meta = _run_metadata.get(project_id, {})
    running = proc is not None and proc.returncode is None
    return {
        "running": running,
        "pid": proc.pid if running else None,
        **meta,
    }


@router.post("/{project_id}/run", dependencies=[Depends(verify_api_key)])
async def start_run(project_id: str, body: Optional[RunRequest] = None):
    """Start the project's run command. Kills any existing run first."""
    project = _get_project(project_id)
    project_path = Path(project["path"])
    if not project_path.exists():
        raise HTTPException(status_code=400, detail=f"Project path does not exist: {project_path}")

    # Determine command
    requested = body.command if body and body.command else None
    saved = project.get("run_command")
    detected = _detect_run_command(project_path)
    command = (requested or saved or detected or "").strip()
    if not command:
        raise HTTPException(
            status_code=400,
            detail="No run command configured and none could be auto-detected. "
                   "Set one via PUT /run/config or include 'command' in the request body."
        )

    # Kill any existing process for this project
    existing = _processes.get(project_id)
    if existing is not None and existing.returncode is None:
        _push_meta(project_id, "killed_previous", pid=existing.pid)
        await _kill_process(existing, project_id)

    # Clear buffer for this new run
    _output_buffers[project_id] = []

    # Swap `python` for the project's venv python if a venv exists
    venv_python = _resolve_python_exe(project)
    actual_command = command
    if venv_python and (command.startswith("python ") or command == "python"):
        # Replace leading `python` with the full venv path
        actual_command = f'"{venv_python}"' + command[len("python"):]

    _push_meta(project_id, "starting", command=command, resolved=actual_command, cwd=str(project_path))

    # Spawn the process. shell=True on Windows so PATH resolution works for npm/cargo/go etc.
    try:
        proc = await asyncio.create_subprocess_shell(
            actual_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_path),
            # Inherit environment so PATH, NODE_PATH, etc. work
            env={**os.environ},
        )
    except Exception as e:
        _push_meta(project_id, "error", message=f"Failed to spawn process: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to spawn process: {e}")

    _processes[project_id] = proc
    _run_metadata[project_id] = {
        "command": command,
        "resolved_command": actual_command,
        "pid": proc.pid,
        "started_at": datetime.utcnow().isoformat(),
        "cwd": str(project_path),
        "exit_code": None,
    }
    _push_meta(project_id, "started", pid=proc.pid, command=command)

    # Ensure an output queue exists
    if project_id not in _output_queues:
        _output_queues[project_id] = asyncio.Queue(maxsize=2000)

    # Stream output in the background
    asyncio.create_task(_stream_process_output(project_id, proc))

    return {"ok": True, "pid": proc.pid, "command": command}


@router.post("/{project_id}/run/stop", dependencies=[Depends(verify_api_key)])
async def stop_run(project_id: str):
    proc = _processes.get(project_id)
    if proc is None or proc.returncode is not None:
        raise HTTPException(status_code=404, detail="No running process for this project")
    _push_meta(project_id, "stopping", pid=proc.pid)
    await _kill_process(proc, project_id)
    _push_meta(project_id, "stopped", pid=proc.pid)
    return {"ok": True, "pid": proc.pid}


@router.get("/{project_id}/run/stream")
async def stream_run_output(project_id: str, request: Request):
    """SSE stream of run output (no auth — EventSource limitation).

    On connect, replays the rolling buffer so the frontend catches up, then
    streams live events until the client disconnects.
    """
    # Ensure project exists (but don't require it to be running)
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    # Ensure queue exists so future events land in it
    if project_id not in _output_queues:
        _output_queues[project_id] = asyncio.Queue(maxsize=2000)

    buffer_snapshot = list(_output_buffers.get(project_id, []))
    queue = _output_queues[project_id]

    async def event_generator() -> AsyncGenerator[str, None]:
        # Replay buffer
        proc = _processes.get(project_id)
        init_payload = {
            "running": proc is not None and proc.returncode is None,
            "pid": proc.pid if proc and proc.returncode is None else None,
            **_run_metadata.get(project_id, {}),
        }
        yield f"data: {json.dumps({'type': 'init', 'payload': init_payload})}\n\n"
        for evt in buffer_snapshot:
            yield f"data: {json.dumps(evt)}\n\n"
            await asyncio.sleep(0.001)

        # Live stream
        while True:
            if await request.is_disconnected():
                break
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(evt)}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


@router.delete("/{project_id}/run/buffer", dependencies=[Depends(verify_api_key)])
async def clear_output_buffer(project_id: str):
    """Clear the stored output buffer (doesn't affect running process)."""
    _output_buffers[project_id] = []
    return {"ok": True}
