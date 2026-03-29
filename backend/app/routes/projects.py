"""Custom Project Locations — create and manage projects at arbitrary paths."""

import uuid
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/projects", tags=["projects"], dependencies=[Depends(verify_api_key)])

_DATA_DIR = Path(r"G:\Model_Mesh\data")
_PROJECTS_FILE = _DATA_DIR / "projects.json"

# ─── Templates ────────────────────────────────────────────────────────────────
TEMPLATES: Dict[str, Dict[str, str]] = {
    "blank": {
        "README.md": "# {name}\n\nCreated with DevForgeAI.\n",
    },
    "python-api": {
        "README.md": "# {name}\n\nFastAPI project created with DevForgeAI.\n",
        "main.py": 'from fastapi import FastAPI\n\napp = FastAPI(title="{name}")\n\n@app.get("/")\ndef root():\n    return {{"name": "{name}", "status": "running"}}\n',
        "requirements.txt": "fastapi>=0.100\nuvicorn>=0.23\n",
        ".gitignore": "__pycache__/\n*.pyc\n.env\nvenv/\n",
    },
    "next-app": {
        "README.md": "# {name}\n\nNext.js project created with DevForgeAI.\n",
        "package.json": '{{\n  "name": "{name_slug}",\n  "version": "0.1.0",\n  "scripts": {{\n    "dev": "next dev",\n    "build": "next build",\n    "start": "next start"\n  }},\n  "dependencies": {{\n    "next": "14.1.0",\n    "react": "18.2.0",\n    "react-dom": "18.2.0"\n  }}\n}}\n',
        ".gitignore": "node_modules/\n.next/\n.env.local\n",
    },
    "cli-tool": {
        "README.md": "# {name}\n\nCLI tool created with DevForgeAI.\n",
        "main.py": 'import argparse\n\ndef main():\n    parser = argparse.ArgumentParser(description="{name}")\n    parser.add_argument("--version", action="version", version="0.1.0")\n    args = parser.parse_args()\n    print("Hello from {name}!")\n\nif __name__ == "__main__":\n    main()\n',
        "requirements.txt": "# Add your dependencies here\n",
        ".gitignore": "__pycache__/\n*.pyc\n.env\n",
    },
}

# ─── Persistence ──────────────────────────────────────────────────────────────
def _load_projects() -> Dict[str, Any]:
    if _PROJECTS_FILE.exists():
        try:
            return json.loads(_PROJECTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_projects(projects: Dict[str, Any]):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _PROJECTS_FILE.write_text(json.dumps(projects, indent=2), encoding="utf-8")


# ─── Models ───────────────────────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str
    path: str
    template: str = "blank"
    description: Optional[str] = None
    agents: Optional[List[str]] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    agents: Optional[List[str]] = None


# ─── Routes ───────────────────────────────────────────────────────────────────
@router.get("/templates")
async def list_templates():
    return {
        "data": [
            {"id": "blank",      "name": "Blank",       "description": "Empty project with README"},
            {"id": "python-api", "name": "Python API",  "description": "FastAPI REST API starter"},
            {"id": "next-app",   "name": "Next.js App", "description": "Next.js 14 frontend starter"},
            {"id": "cli-tool",   "name": "CLI Tool",    "description": "Python CLI tool starter"},
        ]
    }


@router.get("/")
async def list_projects():
    projects = _load_projects()
    data = []
    for p in projects.values():
        path = Path(p["path"])
        p["path_exists"] = path.exists()
        p["file_count"] = len(list(path.rglob("*"))) if path.exists() else 0
        data.append(p)
    data.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return {"data": data, "total": len(data)}


@router.post("/")
async def create_project(body: ProjectCreate):
    projects = _load_projects()

    project_path = Path(body.path)
    if project_path.exists() and any(project_path.iterdir()):
        # Directory exists and is not empty — just register it, don't scaffold
        scaffold = False
    else:
        project_path.mkdir(parents=True, exist_ok=True)
        scaffold = True

    project_id = str(uuid.uuid4())
    name_slug = body.name.lower().replace(" ", "-").replace("_", "-")

    # Scaffold template files
    if scaffold:
        template = TEMPLATES.get(body.template, TEMPLATES["blank"])
        for filename, content in template.items():
            file_path = project_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            rendered = content.format(name=body.name, name_slug=name_slug)
            file_path.write_text(rendered, encoding="utf-8")

    project = {
        "id": project_id,
        "name": body.name,
        "path": str(project_path.resolve()),
        "template": body.template,
        "description": body.description or "",
        "agents": body.agents or [],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "scaffolded": scaffold,
    }

    projects[project_id] = project
    _save_projects(projects)
    return project


@router.get("/{project_id}")
async def get_project(project_id: str):
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    p = projects[project_id]
    p["path_exists"] = Path(p["path"]).exists()
    return p


@router.patch("/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate):
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    if body.name is not None:
        projects[project_id]["name"] = body.name
    if body.description is not None:
        projects[project_id]["description"] = body.description
    if body.agents is not None:
        projects[project_id]["agents"] = body.agents
    projects[project_id]["updated_at"] = datetime.utcnow().isoformat()
    _save_projects(projects)
    return projects[project_id]


@router.delete("/{project_id}")
async def delete_project(project_id: str, delete_files: bool = False):
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")
    project = projects.pop(project_id)
    if delete_files:
        try:
            shutil.rmtree(project["path"])
        except Exception as e:
            logger.warning(f"Failed to delete project files: {e}")
    _save_projects(projects)
    return {"ok": True, "files_deleted": delete_files}


@router.get("/{project_id}/files")
async def list_project_files(project_id: str):
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    path = Path(projects[project_id]["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Project path does not exist on disk")

    IGNORE = {".git", "node_modules", "__pycache__", ".next", "venv", ".venv", "dist", "build"}

    def walk(p: Path, depth: int = 0) -> List[Dict]:
        if depth > 6:
            return []
        result = []
        try:
            entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            for entry in entries:
                if entry.name in IGNORE or entry.name.startswith("."):
                    continue
                item: Dict[str, Any] = {
                    "name": entry.name,
                    "path": str(entry.relative_to(path)),
                    "type": "file" if entry.is_file() else "dir",
                    "size": entry.stat().st_size if entry.is_file() else 0,
                }
                if entry.is_dir():
                    item["children"] = walk(entry, depth + 1)
                result.append(item)
        except PermissionError:
            pass
        return result

    return {"tree": walk(path), "root": str(path)}


@router.get("/{project_id}/files/read")
async def read_project_file(project_id: str, file_path: str):
    projects = _load_projects()
    if project_id not in projects:
        raise HTTPException(status_code=404, detail="Project not found")

    root = Path(projects[project_id]["path"])
    target = (root / file_path).resolve()

    # Security: ensure the target is inside the project root
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if target.stat().st_size > 500_000:
        raise HTTPException(status_code=413, detail="File too large to preview (>500KB)")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": file_path, "content": content, "size": target.stat().st_size}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
