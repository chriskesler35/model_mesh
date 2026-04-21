"""
Skills management routes (installed skills, health checks, etc).
Phase 5-7: Skill lifecycle management.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/skills", tags=["skills"])


@router.get("/installed")
async def get_installed_skills():
    """
    Get list of installed skills.
    Phase 5: Returns empty list (no install logic yet).
    Phase 6+: Will return actual installed skills with health status.
    """
    # Phase 5: Return empty list
    # This will be populated in Phase 6 when install endpoints are created
    return []
