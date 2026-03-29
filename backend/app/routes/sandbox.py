"""Process Isolation & Sandboxing — per-project venvs, snapshots, rollbacks."""

import json
import subprocess
import asyncio
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/sandbox", tags=["sandbox"], dependencies=[Depends(verify_api_key)])

_DATA_DIR = Path(r"G:\Model_Mesh\data")
_PROJECTS_FILE = _DATA_DIR / "projects.json"
_SANDBOX_FILE = _DATA_DIR / "sandbox_state.json"

PYTHON_EXE = r"C:\Python314\python.exe"


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _load_projects() -> Dict[str, Any]:
    if _PROJECTS_FILE.exists():
        try:
            return json.loads(_PROJECTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _load_sandbox() -> Dict[str, Any]:
    if _SANDBOX_FILE.exists():
        try:
            return json.loads(_SANDBOX_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_sandbox(data: Dict[str, Any]):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SANDBOX_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _get_project(project_id: str) -> Dict[str, Any]:
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return projects[project_id]


def _run_cmd(cmd: List[str], cwd: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
    """Run a subprocess and return stdout/stderr/returncode."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "ok": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Command timed out", "ok": False}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e), "ok": False}


# ─── Models ───────────────────────────────────────────────────────────────────
class EnvCreate(BaseModel):
    requirements: Optional[str] = None  # pip packages to install, space-separated


class SnapshotCreate(BaseModel):
    message: str = "DevForgeAI snapshot"


class RollbackRequest(BaseModel):
    commit_hash: str


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/status")
async def get_sandbox_status(project_id: str):
    """Get sandbox status for a project."""
    project = _get_project(project_id)
    path = Path(project["path"])
    sandbox = _load_sandbox()
    state = sandbox.get(project_id, {})

    venv_path = path / ".venv"
    venv_exists = venv_path.exists()

    # Check git status
    git_ok = _run_cmd(["git", "status", "--short"], cwd=str(path))
    git_initialized = git_ok["ok"]

    # Get snapshots (git log)
    snapshots = []
    if git_initialized:
        log = _run_cmd(
            ["git", "log", "--oneline", "--max-count=10"],
            cwd=str(path)
        )
        if log["ok"] and log["stdout"]:
            for line in log["stdout"].splitlines():
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    snapshots.append({"hash": parts[0], "message": parts[1]})

    return {
        "project_id": project_id,
        "project_name": project["name"],
        "project_path": str(path),
        "path_exists": path.exists(),
        "venv_exists": venv_exists,
        "venv_path": str(venv_path) if venv_exists else None,
        "git_initialized": git_initialized,
        "git_status": git_ok["stdout"] if git_initialized else None,
        "snapshots": snapshots,
        "env_vars": state.get("env_vars", {}),
        "installed_packages": state.get("installed_packages", []),
    }


@router.post("/projects/{project_id}/venv")
async def create_venv(project_id: str, body: EnvCreate):
    """Create a Python virtual environment for the project."""
    project = _get_project(project_id)
    path = Path(project["path"])

    if not path.exists():
        raise HTTPException(status_code=400, detail="Project path does not exist on disk")

    venv_path = path / ".venv"
    if venv_path.exists():
        return {"ok": True, "message": "Virtual environment already exists", "venv_path": str(venv_path)}

    # Create venv
    result = _run_cmd([PYTHON_EXE, "-m", "venv", str(venv_path)])
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=f"Failed to create venv: {result['stderr']}")

    # Install packages if requested
    installed = []
    if body.requirements:
        pip_exe = venv_path / "Scripts" / "pip.exe"
        packages = body.requirements.split()
        install_result = _run_cmd([str(pip_exe), "install"] + packages, cwd=str(path))
        if install_result["ok"]:
            installed = packages

    # Save state
    sandbox = _load_sandbox()
    sandbox.setdefault(project_id, {})["installed_packages"] = installed
    sandbox[project_id]["venv_created_at"] = datetime.utcnow().isoformat()
    _save_sandbox(sandbox)

    return {
        "ok": True,
        "venv_path": str(venv_path),
        "installed_packages": installed,
        "message": f"Virtual environment created at {venv_path}"
    }


@router.delete("/projects/{project_id}/venv")
async def delete_venv(project_id: str):
    """Remove the virtual environment for a project."""
    project = _get_project(project_id)
    venv_path = Path(project["path"]) / ".venv"
    if not venv_path.exists():
        raise HTTPException(status_code=404, detail="No virtual environment found")
    shutil.rmtree(str(venv_path))
    return {"ok": True, "message": "Virtual environment removed"}


@router.post("/projects/{project_id}/install")
async def install_packages(project_id: str, body: EnvCreate):
    """Install packages into the project's venv."""
    project = _get_project(project_id)
    path = Path(project["path"])
    pip_exe = path / ".venv" / "Scripts" / "pip.exe"

    if not pip_exe.exists():
        raise HTTPException(status_code=400, detail="No virtual environment — create one first")
    if not body.requirements:
        raise HTTPException(status_code=400, detail="No packages specified")

    packages = body.requirements.split()
    result = _run_cmd([str(pip_exe), "install"] + packages, cwd=str(path), timeout=120)
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=f"pip install failed: {result['stderr']}")

    sandbox = _load_sandbox()
    existing = sandbox.get(project_id, {}).get("installed_packages", [])
    sandbox.setdefault(project_id, {})["installed_packages"] = list(set(existing + packages))
    _save_sandbox(sandbox)

    return {"ok": True, "installed": packages, "output": result["stdout"]}


@router.post("/projects/{project_id}/git/init")
async def git_init(project_id: str):
    """Initialize git in the project directory."""
    project = _get_project(project_id)
    path = Path(project["path"])
    if not path.exists():
        raise HTTPException(status_code=400, detail="Project path does not exist")

    result = _run_cmd(["git", "init"], cwd=str(path))
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=f"git init failed: {result['stderr']}")

    # Create .gitignore if it doesn't exist
    gitignore = path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".venv/\n__pycache__/\n*.pyc\n.env\nnode_modules/\n.next/\n", encoding="utf-8")

    return {"ok": True, "message": "Git repository initialized"}


@router.post("/projects/{project_id}/snapshot")
async def create_snapshot(project_id: str, body: SnapshotCreate):
    """Create a git snapshot (commit) of the current project state."""
    project = _get_project(project_id)
    path = Path(project["path"])

    # Stage all changes
    add_result = _run_cmd(["git", "add", "-A"], cwd=str(path))
    if not add_result["ok"]:
        raise HTTPException(status_code=500, detail=f"git add failed: {add_result['stderr']}")

    # Commit
    commit_result = _run_cmd(
        ["git", "commit", "-m", body.message, "--allow-empty"],
        cwd=str(path)
    )
    if not commit_result["ok"]:
        raise HTTPException(status_code=500, detail=f"git commit failed: {commit_result['stderr']}")

    # Get the new commit hash
    hash_result = _run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=str(path))

    return {
        "ok": True,
        "message": body.message,
        "commit_hash": hash_result["stdout"] if hash_result["ok"] else "unknown",
        "output": commit_result["stdout"]
    }


@router.post("/projects/{project_id}/rollback")
async def rollback_snapshot(project_id: str, body: RollbackRequest):
    """Rollback the project to a previous snapshot."""
    project = _get_project(project_id)
    path = Path(project["path"])

    # Create a safety snapshot before rolling back
    _run_cmd(["git", "add", "-A"], cwd=str(path))
    _run_cmd(["git", "commit", "-m", "Auto-snapshot before rollback", "--allow-empty"], cwd=str(path))

    result = _run_cmd(
        ["git", "checkout", body.commit_hash, "--", "."],
        cwd=str(path)
    )
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {result['stderr']}")

    return {
        "ok": True,
        "message": f"Rolled back to {body.commit_hash}",
        "output": result["stdout"]
    }


@router.get("/projects/{project_id}/env-vars")
async def get_env_vars(project_id: str):
    """Get environment variables for a project (.env file)."""
    project = _get_project(project_id)
    env_path = Path(project["path"]) / ".env"
    env_vars = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()
    return {"env_vars": env_vars, "path": str(env_path)}


@router.post("/projects/{project_id}/env-vars")
async def set_env_vars(project_id: str, body: Dict[str, str]):
    """Set environment variables for a project (writes .env file)."""
    project = _get_project(project_id)
    env_path = Path(project["path"]) / ".env"
    lines = [f"{k}={v}" for k, v in body.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "env_vars": body}
