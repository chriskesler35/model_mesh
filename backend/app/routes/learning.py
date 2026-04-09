"""Learning / auto-tuning endpoints — feedback analysis, routing suggestions, and usage patterns."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.middleware.auth import verify_api_key, current_user
from app.services.learning import (
    analyze_feedback,
    get_pending_suggestions,
    apply_suggestion,
    dismiss_suggestion,
    detect_usage_patterns,
    get_pattern_suggestions,
    set_pattern_tracking,
    analyze_response_style,
    get_style_profile,
    update_style_profile,
    format_style_injection,
)

router = APIRouter(prefix="/v1/learning", tags=["learning"], dependencies=[Depends(verify_api_key)])


@router.get("/suggestions")
async def list_suggestions(
    status: Optional[str] = Query(default="pending"),
    db: AsyncSession = Depends(get_db),
):
    """List learning suggestions, filtered by status (default: pending)."""
    if status == "pending":
        suggestions = await get_pending_suggestions(db)
    else:
        from sqlalchemy import select
        from app.models.learning_suggestion import LearningSuggestion

        stmt = select(LearningSuggestion).order_by(LearningSuggestion.created_at.desc())
        if status:
            stmt = stmt.where(LearningSuggestion.status == status)
        result = await db.execute(stmt)
        suggestions = [s.to_dict() for s in result.scalars().all()]

    return {"suggestions": suggestions, "count": len(suggestions)}


@router.post("/analyze")
async def trigger_analysis(
    min_entries: int = Query(default=20, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Trigger feedback analysis to generate routing suggestions."""
    new_suggestions = await analyze_feedback(db, min_entries=min_entries)
    return {
        "new_suggestions": new_suggestions,
        "count": len(new_suggestions),
    }


@router.post("/suggestions/{suggestion_id}/apply")
async def apply_suggestion_endpoint(
    suggestion_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Apply a pending learning suggestion."""
    try:
        result = await apply_suggestion(db, suggestion_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion_endpoint(
    suggestion_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a pending learning suggestion."""
    try:
        result = await dismiss_suggestion(db, suggestion_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


# ---------------------------------------------------------------------------
# Usage-pattern endpoints (E12.3)
# ---------------------------------------------------------------------------

class PatternOptOutBody(BaseModel):
    enabled: bool


@router.get("/patterns")
async def get_usage_patterns(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return detected usage patterns for the current user."""
    user = current_user(request)
    user_id = user["id"]
    patterns = await detect_usage_patterns(db, user_id)
    suggestions = await get_pattern_suggestions(db, user_id)
    return {"patterns": patterns, "suggestions": suggestions}


@router.put("/patterns/opt-out")
async def toggle_pattern_tracking(
    body: PatternOptOutBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Toggle pattern tracking for the current user.

    Send `{"enabled": false}` to opt out, `{"enabled": true}` to opt back in.
    """
    user = current_user(request)
    user_id = user["id"]
    result = await set_pattern_tracking(db, user_id, body.enabled)
    return result


# ---------------------------------------------------------------------------
# Adaptive style profile endpoints (E12.4)
# ---------------------------------------------------------------------------

class StyleOverrideBody(BaseModel):
    verbosity: Optional[int] = None
    formality: Optional[int] = None
    code_style: Optional[str] = None
    response_length_preference: Optional[str] = None
    example_preference: Optional[str] = None


@router.get("/style")
async def get_style(
    request: Request,
    analyze: bool = Query(default=False, description="Re-analyze before returning"),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's learned style profile."""
    user = current_user(request)
    user_id = user["id"]
    if analyze:
        profile = await analyze_response_style(db, user_id)
    else:
        profile = await get_style_profile(db, user_id)
    injection = format_style_injection(profile)
    return {"style": profile, "injection": injection}


@router.patch("/style")
async def patch_style(
    body: StyleOverrideBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Manually override style profile dimensions."""
    user = current_user(request)
    user_id = user["id"]
    overrides = body.model_dump(exclude_none=True)
    if not overrides:
        raise HTTPException(status_code=400, detail="No style dimensions provided")
    try:
        profile = await update_style_profile(db, user_id, overrides)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    injection = format_style_injection(profile)
    return {"style": profile, "injection": injection}
