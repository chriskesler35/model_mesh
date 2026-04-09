"""Learning analysis service — analyze feedback to generate routing suggestions."""

import uuid
import logging
from datetime import datetime
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import Feedback
from app.models.learning_suggestion import LearningSuggestion

logger = logging.getLogger(__name__)


async def analyze_feedback(db: AsyncSession, min_entries: int = 20) -> list[dict]:
    """Analyze feedback patterns and create routing suggestions.

    Groups feedback by model_id, calculates satisfaction rate,
    and creates suggestions for models with >= 90% positive ratings
    and at least min_entries feedback entries.
    """
    # Group feedback by model_id, compute counts
    stmt = (
        select(
            Feedback.model_id,
            func.count(Feedback.id).label("total"),
            func.sum(case((Feedback.rating >= 4, 1), else_=0)).label("positive"),
        )
        .where(Feedback.model_id.isnot(None))
        .group_by(Feedback.model_id)
        .having(func.count(Feedback.id) >= min_entries)
    )
    result = await db.execute(stmt)
    rows = result.all()

    new_suggestions: list[dict] = []

    for row in rows:
        model_id = row.model_id
        total = row.total
        positive = row.positive or 0
        satisfaction_rate = positive / total if total else 0.0

        if satisfaction_rate < 0.9:
            continue

        # Check if a pending/applied suggestion already exists for this model
        existing = await db.execute(
            select(LearningSuggestion).where(
                LearningSuggestion.model_id == model_id,
                LearningSuggestion.status.in_(["pending", "applied"]),
            )
        )
        if existing.scalars().first():
            continue

        suggestion = LearningSuggestion(
            id=uuid.uuid4(),
            suggestion_type="model_preference",
            model_id=model_id,
            task_type=None,
            confidence=round(satisfaction_rate, 4),
            reason=(
                f"Model '{model_id}' received {positive}/{total} positive ratings "
                f"({satisfaction_rate:.0%} satisfaction rate) across {total} feedback entries."
            ),
            current_value=None,
            suggested_value=f"prefer:{model_id}",
            status="pending",
        )
        db.add(suggestion)
        new_suggestions.append(suggestion.to_dict())
        logger.info("Created learning suggestion for model %s (%.0f%% satisfaction)", model_id, satisfaction_rate * 100)

    if new_suggestions:
        await db.commit()

    return new_suggestions


async def get_pending_suggestions(db: AsyncSession) -> list[dict]:
    """Return all pending learning suggestions."""
    result = await db.execute(
        select(LearningSuggestion)
        .where(LearningSuggestion.status == "pending")
        .order_by(LearningSuggestion.created_at.desc())
    )
    return [s.to_dict() for s in result.scalars().all()]


async def apply_suggestion(db: AsyncSession, suggestion_id: str) -> dict:
    """Apply a learning suggestion — mark as applied with timestamp."""
    result = await db.execute(
        select(LearningSuggestion).where(LearningSuggestion.id == suggestion_id)
    )
    suggestion = result.scalars().first()
    if not suggestion:
        raise ValueError(f"Suggestion {suggestion_id} not found")

    suggestion.status = "applied"
    suggestion.applied_at = datetime.utcnow()
    await db.commit()
    await db.refresh(suggestion)
    return suggestion.to_dict()


async def dismiss_suggestion(db: AsyncSession, suggestion_id: str) -> dict:
    """Dismiss a learning suggestion."""
    result = await db.execute(
        select(LearningSuggestion).where(LearningSuggestion.id == suggestion_id)
    )
    suggestion = result.scalars().first()
    if not suggestion:
        raise ValueError(f"Suggestion {suggestion_id} not found")

    suggestion.status = "dismissed"
    await db.commit()
    await db.refresh(suggestion)
    return suggestion.to_dict()
