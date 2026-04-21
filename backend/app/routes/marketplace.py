"""
Marketplace routes for skill discovery and catalog management.
Phase 5: Frontend-first discovery with mocked API responses.
"""

import json
import os
from typing import Optional, List
from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/marketplace", tags=["marketplace"])

# Load skills catalog on startup
_SKILLS_CATALOG: Optional[List[dict]] = None


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


# Initialize catalog on module load
load_skills_catalog()
