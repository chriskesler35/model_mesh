"""
Marketplace routes for skill discovery and catalog management.
Phase 5-6: Frontend-first discovery + mock install orchestrator.
"""

import json
import os
import uuid
import time
import asyncio
import random
from typing import Optional, List, Dict
from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/marketplace", tags=["marketplace"])

# Load skills catalog on startup
_SKILLS_CATALOG: Optional[List[dict]] = None

# In-memory install job tracking (Phase 6 mock)
_INSTALL_JOBS: Dict[str, dict] = {}


def load_skills_catalog():
    """Load the skills catalog JSON file into memory."""
    global _SKILLS_CATALOG
    catalog_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "skills_catalog.json"
    )
    try:
        with open(catalog_path, 'r') as f:
            _SKILLS_CATALOG = json.load(f)
    except FileNotFoundError:
        _SKILLS_CATALOG = []
        print(f"Warning: skills_catalog.json not found at {catalog_path}")


class SkillSearchRequest(BaseModel):
    """Request model for skill search with filters."""
    search_query: Optional[str] = None
    use_cases: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    complexity: Optional[str] = None
    trust_level: Optional[str] = None


class SkillResponse(BaseModel):
    """Response model for a single skill."""
    skill_id: str
    name: str
    description: str
    use_cases: List[str]
    languages: List[str]
    complexity: str
    trust_level: str
    version: str
    install_url: str
    manifest_url: str
    icon_url: str


class SkillSearchResponse(BaseModel):
    """Response model for skill search results."""
    total: int
    results: List[SkillResponse]


class FilterOptions(BaseModel):
    """Available filter options."""
    use_cases: List[str]
    languages: List[str]
    complexity_levels: List[str]
    trust_levels: List[str]


class InstallProgressResponse(BaseModel):
    """Response model for install progress."""
    job_id: str
    skill_id: str
    status: str  # downloading, validating, extracting, checking, finalizing, success, failed
    current_step: int
    progress: int
    step_messages: Dict[str, str]
    error: Optional[str] = None
    failed_step: Optional[int] = None
    can_retry: bool = False


@router.get("/filters", response_model=FilterOptions)
async def get_filter_options():
    """
    Get available filter options for the marketplace.
    
    Returns:
    - use_cases: List of all unique use cases across skills
    - languages: List of all unique languages
    - complexity_levels: List of complexity levels (beginner, intermediate, advanced)
    - trust_levels: List of trust levels (verified, community, experimental)
    """
    if not _SKILLS_CATALOG:
        load_skills_catalog()
    
    use_cases = set()
    languages = set()
    complexity_levels = set()
    trust_levels = set()
    
    for skill in _SKILLS_CATALOG:
        use_cases.update(skill.get("use_cases", []))
        languages.update(skill.get("languages", []))
        complexity_levels.add(skill.get("complexity", ""))
        trust_levels.add(skill.get("trust_level", ""))
    
    return FilterOptions(
        use_cases=sorted(list(use_cases)),
        languages=sorted(list(languages)),
        complexity_levels=sorted(list(complexity_levels)),
        trust_levels=sorted(list(trust_levels))
    )


@router.get("/skills", response_model=SkillSearchResponse)
async def search_skills(
    search_query: Optional[str] = Query(None, description="Text to search in name/description"),
    use_cases: Optional[str] = Query(None, description="Comma-separated use cases (OR logic)"),
    languages: Optional[str] = Query(None, description="Comma-separated languages (OR logic)"),
    complexity: Optional[str] = Query(None, description="Single complexity level (exact match)"),
    trust_level: Optional[str] = Query(None, description="Single trust level (exact match)"),
):
    """
    Search and filter skills from the marketplace catalog.
    
    Query parameters:
    - search_query: Text search (searches name and description)
    - use_cases: Comma-separated list (OR logic — match any)
    - languages: Comma-separated list (OR logic — match any)
    - complexity: Single value (beginner, intermediate, advanced)
    - trust_level: Single value (verified, community, experimental)
    
    Returns:
    - total: Total number of matching skills
    - results: Array of matching skill details
    """
    if not _SKILLS_CATALOG:
        load_skills_catalog()
    
    results = _SKILLS_CATALOG.copy()
    
    # Text search (name or description)
    if search_query:
        query_lower = search_query.lower()
        results = [
            s for s in results
            if query_lower in s.get("name", "").lower()
            or query_lower in s.get("description", "").lower()
        ]
    
    # Use cases filter (OR logic)
    if use_cases:
        use_cases_list = [u.strip() for u in use_cases.split(",")]
        results = [
            s for s in results
            if any(uc in s.get("use_cases", []) for uc in use_cases_list)
        ]
    
    # Languages filter (OR logic)
    if languages:
        languages_list = [l.strip() for l in languages.split(",")]
        results = [
            s for s in results
            if any(lang in s.get("languages", []) for lang in languages_list)
        ]
    
    # Complexity filter (exact match)
    if complexity:
        results = [s for s in results if s.get("complexity") == complexity]
    
    # Trust level filter (exact match)
    if trust_level:
        results = [s for s in results if s.get("trust_level") == trust_level]
    
    # Convert to SkillResponse objects
    skill_responses = [
        SkillResponse(**skill) for skill in results
    ]
    
    return SkillSearchResponse(
        total=len(skill_responses),
        results=skill_responses
    )


@router.get("/skill/{skill_id}", response_model=SkillResponse)
async def get_skill_detail(skill_id: str):
    """
    Get detailed information for a specific skill.
    
    Args:
    - skill_id: The unique skill identifier (e.g., 'langchain', 'bmad-core')
    
    Returns:
    - Full skill metadata including description, requirements, URLs
    
    Raises:
    - 404 if skill not found
    """
    if not _SKILLS_CATALOG:
        load_skills_catalog()
    
    for skill in _SKILLS_CATALOG:
        if skill.get("skill_id") == skill_id:
            return SkillResponse(**skill)
    
    # Not found
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")


@router.post("/skill/{skill_id}/install")
async def start_install(skill_id: str):
    """
    Start a mock install for a skill.
    
    Args:
    - skill_id: The unique skill identifier
    
    Returns:
    - job_id: Unique identifier for this install job
    
    Workflow:
    1. Validate skill exists
    2. Create install job with start time
    3. Return job_id for polling
    """
    if not _SKILLS_CATALOG:
        load_skills_catalog()
    
    # Validate skill exists
    skill_found = any(s.get("skill_id") == skill_id for s in _SKILLS_CATALOG)
    if not skill_found:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    
    # Create install job
    job_id = str(uuid.uuid4())
    _INSTALL_JOBS[job_id] = {
        "skill_id": skill_id,
        "start_time": time.time(),
        "status": "downloading",
        "current_step": 0,
        "progress": 0,
        "failed": False,
        "failed_step": None,
        "failure_point": random.randint(3, 4) if random.random() < 0.2 else None,  # 20% failure chance
    }
    
    return {"job_id": job_id}


@router.get("/skill/{skill_id}/install/progress/{job_id}", response_model=InstallProgressResponse)
async def get_install_progress(skill_id: str, job_id: str):
    """
    Poll the progress of an ongoing install job.
    
    Mock behavior:
    - Step 0 (0-2s):    Download (0% → 25%)
    - Step 1 (2-4s):    Validate (25% → 50%)
    - Step 2 (4-6s):    Extract (50% → 75%)
    - Step 3 (6-8s):    Health Check (75% → 90%)
    - Step 4 (8-10s):   Finalize (90% → 100%)
    - [10s+]:           Success or Failure
    
    Args:
    - skill_id: The unique skill identifier
    - job_id: The install job ID to poll
    
    Returns:
    - Current job status with progress, current step, and step messages
    """
    if job_id not in _INSTALL_JOBS:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    job = _INSTALL_JOBS[job_id]
    elapsed = time.time() - job["start_time"]
    
    # Step messages
    step_names = [
        "Downloading",
        "Validating",
        "Extracting",
        "Running Health Check",
        "Finalizing",
    ]
    
    step_messages = {}
    
    # Determine current step and progress based on elapsed time
    # Each step is ~2 seconds
    if elapsed < 2:
        step = 0
        progress = int(25 * (elapsed / 2))
    elif elapsed < 4:
        step = 1
        progress = 25 + int(25 * ((elapsed - 2) / 2))
    elif elapsed < 6:
        step = 2
        progress = 50 + int(25 * ((elapsed - 4) / 2))
    elif elapsed < 8:
        step = 3
        progress = 75 + int(15 * ((elapsed - 6) / 2))
    elif elapsed < 10:
        step = 4
        progress = 90 + int(10 * ((elapsed - 8) / 2))
    else:
        # Install complete or failed
        if job["failure_point"] is not None and job["failure_point"] == 3:
            # Simulated failure on health check
            return InstallProgressResponse(
                job_id=job_id,
                skill_id=skill_id,
                status="failed",
                current_step=3,
                progress=75,
                step_messages={
                    "0": f"✓ Downloaded {job['skill_id']} v1.0.0",
                    "1": f"✓ Validated package integrity",
                    "2": f"✓ Extracted files to site-packages",
                    "3": f"✗ Health check failed: ModuleNotFoundError: No module named '{job['skill_id']}'",
                },
                error=f"Health check failed: ModuleNotFoundError: No module named '{job['skill_id']}'",
                failed_step=3,
                can_retry=True,
            )
        else:
            # Success
            step = 4
            progress = 100
            for i, name in enumerate(step_names):
                step_messages[str(i)] = f"✓ {name.capitalize()} {job['skill_id']} completed"
            
            return InstallProgressResponse(
                job_id=job_id,
                skill_id=skill_id,
                status="success",
                current_step=5,
                progress=100,
                step_messages=step_messages,
                error=None,
                can_retry=False,
            )
    
    # Build step messages for in-progress steps
    for i in range(step + 1):
        if i < step:
            step_messages[str(i)] = f"✓ {step_names[i].capitalize()} {job['skill_id']} completed"
        elif i == step:
            step_messages[str(i)] = f"→ {step_names[i].capitalize()} {job['skill_id']}..."
    
    return InstallProgressResponse(
        job_id=job_id,
        skill_id=skill_id,
        status=["downloading", "validating", "extracting", "checking", "finalizing"][step],
        current_step=step,
        progress=min(progress, 100),
        step_messages=step_messages,
        error=None,
        can_retry=False,
    )


# Initialize catalog on module load
load_skills_catalog()
