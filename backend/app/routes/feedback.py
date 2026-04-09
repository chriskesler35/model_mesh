"""Feedback endpoints — collect and summarize user satisfaction ratings."""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.middleware.auth import verify_api_key
from app.models.feedback import Feedback

import uuid

router = APIRouter(prefix="/v1/feedback", tags=["feedback"], dependencies=[Depends(verify_api_key)])


class FeedbackCreate(BaseModel):
    message_id: str
    conversation_id: Optional[str] = None
    model_id: Optional[str] = None
    rating: int  # 1 = thumbs down, 5 = thumbs up
    feedback_text: Optional[str] = None


@router.post("")
async def create_feedback(
    body: FeedbackCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Store user feedback on an AI response."""
    if body.rating not in (1, 5):
        raise HTTPException(status_code=422, detail="Rating must be 1 (thumbs down) or 5 (thumbs up)")

    user = getattr(request.state, "user", {})
    user_id = user.get("id", "anonymous") if isinstance(user, dict) else "anonymous"

    feedback = Feedback(
        id=uuid.uuid4(),
        user_id=user_id,
        message_id=body.message_id,
        conversation_id=body.conversation_id,
        model_id=body.model_id,
        rating=body.rating,
        feedback_text=body.feedback_text,
    )
    db.add(feedback)
    await db.commit()

    return {"id": str(feedback.id), "status": "saved"}


@router.get("")
async def get_feedback_summary(
    model_id: Optional[str] = Query(default=None),
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Get feedback summary, optionally filtered by model."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    if model_id:
        result = await db.execute(
            text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN rating = 5 THEN 1 END) as positive,
                    COUNT(CASE WHEN rating = 1 THEN 1 END) as negative
                FROM feedback
                WHERE model_id = :model_id AND created_at >= :since
            """),
            {"model_id": model_id, "since": since},
        )
        row = result.fetchone()
        total = row[0] if row else 0
        positive = row[1] if row else 0
        negative = row[2] if row else 0

        return {
            "model_id": model_id,
            "total": total,
            "positive": positive,
            "negative": negative,
            "satisfaction_rate": round(positive / total * 100, 1) if total > 0 else 0,
            "period_days": days,
        }

    # All models grouped
    result = await db.execute(
        text("""
            SELECT
                model_id,
                COUNT(*) as total,
                COUNT(CASE WHEN rating = 5 THEN 1 END) as positive,
                COUNT(CASE WHEN rating = 1 THEN 1 END) as negative
            FROM feedback
            WHERE created_at >= :since
            GROUP BY model_id
        """),
        {"since": since},
    )
    rows = result.fetchall()
    return {
        "by_model": [
            {
                "model_id": row[0],
                "total": row[1],
                "positive": row[2],
                "negative": row[3],
                "satisfaction_rate": round(row[2] / row[1] * 100, 1) if row[1] > 0 else 0,
            }
            for row in rows
        ],
        "period_days": days,
    }
