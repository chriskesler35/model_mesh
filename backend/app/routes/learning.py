"""Learning / auto-tuning endpoints — feedback analysis and routing suggestions."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.middleware.auth import verify_api_key
from app.services.learning import (
    analyze_feedback,
    get_pending_suggestions,
    apply_suggestion,
    dismiss_suggestion,
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
