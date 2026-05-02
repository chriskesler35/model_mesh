"""Skills management routes for installed skills lifecycle."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/skills", tags=["skills"])

_ROOT_DIR = Path(__file__).resolve().parents[3]
_DATA_DIR = _ROOT_DIR / "data"
_INSTALLED_SKILLS_FILE = _DATA_DIR / "installed_skills.json"
_CATALOG_FILE = _ROOT_DIR / "backend" / "skills_catalog.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_data_file() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _INSTALLED_SKILLS_FILE.exists():
        _INSTALLED_SKILLS_FILE.write_text("[]", encoding="utf-8")


def _read_catalog() -> list[dict]:
    try:
        return json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _read_installed_skills() -> list[dict]:
    _ensure_data_file()
    try:
        payload = json.loads(_INSTALLED_SKILLS_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
    except Exception:
        pass
    return []


def _write_installed_skills(skills: list[dict]) -> None:
    _ensure_data_file()
    _INSTALLED_SKILLS_FILE.write_text(json.dumps(skills, indent=2), encoding="utf-8")


def _default_health(enabled: bool) -> str:
    return "healthy" if enabled else "unknown"


def _normalize_installed_skill(skill: dict) -> dict:
    enabled = bool(skill.get("enabled", True))
    return {
        "skill_id": skill.get("skill_id", ""),
        "name": skill.get("name") or skill.get("skill_id") or "unknown",
        "description": skill.get("description", ""),
        "version": skill.get("version", "unknown"),
        "use_cases": skill.get("use_cases") or [],
        "languages": skill.get("languages") or [],
        "complexity": skill.get("complexity", "unknown"),
        "trust_level": skill.get("trust_level", "community"),
        "install_url": skill.get("install_url", ""),
        "manifest_url": skill.get("manifest_url", ""),
        "installed_at": skill.get("installed_at") or _utc_now_iso(),
        "health_status": skill.get("health_status") or _default_health(enabled),
        "enabled": enabled,
    }


def _find_catalog_skill(skill_id: str) -> Optional[dict]:
    for skill in _read_catalog():
        if skill.get("skill_id") == skill_id:
            return skill
    return None


class AddSkillRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    use_cases: Optional[list[str]] = None
    languages: Optional[list[str]] = None
    complexity: Optional[str] = None
    trust_level: Optional[str] = None
    install_url: Optional[str] = None
    manifest_url: Optional[str] = None


class ToggleSkillRequest(BaseModel):
    enabled: Optional[bool] = None


@router.get("/installed")
async def get_installed_skills():
    skills = [_normalize_installed_skill(s) for s in _read_installed_skills()]
    skills.sort(key=lambda x: x.get("installed_at", ""), reverse=True)
    return skills


@router.post("/{skill_id}/add")
async def add_installed_skill(skill_id: str, body: Optional[AddSkillRequest] = None):
    catalog_skill = _find_catalog_skill(skill_id)
    if not catalog_skill and body is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found in catalog")

    payload = (body.model_dump(exclude_none=True) if body else {})
    source = {**(catalog_skill or {}), **payload, "skill_id": skill_id}
    normalized = _normalize_installed_skill(source)

    skills = _read_installed_skills()
    existing_idx = next((i for i, s in enumerate(skills) if s.get("skill_id") == skill_id), None)
    if existing_idx is None:
        skills.append(normalized)
    else:
        preserved_installed_at = skills[existing_idx].get("installed_at") or normalized["installed_at"]
        skills[existing_idx] = {
            **normalized,
            "installed_at": preserved_installed_at,
        }

    _write_installed_skills(skills)
    return {"ok": True, "skill": normalized}


@router.post("/{skill_id}/remove")
async def remove_installed_skill(skill_id: str):
    skills = _read_installed_skills()
    next_skills = [s for s in skills if s.get("skill_id") != skill_id]
    if len(next_skills) == len(skills):
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' is not installed")
    _write_installed_skills(next_skills)
    return {"ok": True, "removed": skill_id}


@router.post("/{skill_id}/toggle")
async def toggle_installed_skill(skill_id: str, body: ToggleSkillRequest):
    skills = _read_installed_skills()
    for idx, skill in enumerate(skills):
        if skill.get("skill_id") != skill_id:
            continue
        current = _normalize_installed_skill(skill)
        next_enabled = (not current["enabled"]) if body.enabled is None else body.enabled
        current["enabled"] = bool(next_enabled)
        current["health_status"] = _default_health(current["enabled"])
        skills[idx] = current
        _write_installed_skills(skills)
        return {"ok": True, "skill": current}

    raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' is not installed")


@router.get("/{skill_id}/health")
async def get_installed_skill_health(skill_id: str):
    skills = _read_installed_skills()
    for skill in skills:
        if skill.get("skill_id") == skill_id:
            normalized = _normalize_installed_skill(skill)
            return {
                "skill_id": skill_id,
                "health_status": normalized["health_status"],
                "enabled": normalized["enabled"],
                "checked_at": _utc_now_iso(),
            }
    raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' is not installed")


@router.post("/{skill_id}/update")
async def update_installed_skill(skill_id: str):
    skills = _read_installed_skills()
    catalog_skill = _find_catalog_skill(skill_id)
    if not catalog_skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found in catalog")

    for idx, skill in enumerate(skills):
        if skill.get("skill_id") != skill_id:
            continue
        current = _normalize_installed_skill(skill)
        updated = {
            **current,
            **_normalize_installed_skill({**catalog_skill, "skill_id": skill_id}),
            "installed_at": current.get("installed_at") or _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
        skills[idx] = updated
        _write_installed_skills(skills)
        return {"ok": True, "skill": updated}

    raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' is not installed")
