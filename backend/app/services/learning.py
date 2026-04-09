"""Learning analysis service — analyze feedback to generate routing suggestions and detect usage patterns."""

import uuid
import logging
from datetime import datetime
from collections import defaultdict
from sqlalchemy import select, func, case, extract, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import Feedback
from app.models.learning_suggestion import LearningSuggestion
from app.models.request_log import RequestLog
from app.models.conversation import Conversation
from app.models.model import Model
from app.models.persona import Persona
from app.models.user_profile import UserProfile

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


# ---------------------------------------------------------------------------
# Usage-pattern detection (E12.3)
# ---------------------------------------------------------------------------

async def _is_pattern_tracking_enabled(db: AsyncSession, user_id: str) -> bool:
    """Check if pattern tracking is enabled for a user."""
    result = await db.execute(select(UserProfile).limit(1))
    profile = result.scalars().first()
    if not profile:
        return True  # default: enabled
    prefs = profile.preferences or {}
    return prefs.get("pattern_tracking_enabled", True)


async def set_pattern_tracking(db: AsyncSession, user_id: str, enabled: bool) -> dict:
    """Toggle pattern tracking opt-out for a user."""
    result = await db.execute(select(UserProfile).limit(1))
    profile = result.scalars().first()
    if not profile:
        profile = UserProfile(name="User", preferences={})
        db.add(profile)

    prefs = dict(profile.preferences or {})
    prefs["pattern_tracking_enabled"] = enabled
    profile.preferences = prefs
    await db.commit()
    await db.refresh(profile)
    return {"pattern_tracking_enabled": enabled}


async def detect_usage_patterns(db: AsyncSession, user_id: str) -> dict:
    """Analyze request logs, conversations, and model usage to detect patterns.

    Returns a dict with pattern categories:
      - model_preferences: which models are used most
      - time_patterns: peak hours and day-of-week distribution
      - session_length: conversation length statistics
      - task_distribution: usage by persona (proxy for task type)
    """
    if not await _is_pattern_tracking_enabled(db, user_id):
        return {"opted_out": True, "patterns": {}}

    patterns: dict = {}

    # -- Model preferences ------------------------------------------------
    model_counts_stmt = (
        select(
            RequestLog.model_id,
            func.count(RequestLog.id).label("cnt"),
        )
        .where(RequestLog.model_id.isnot(None), RequestLog.success.is_(True))
        .group_by(RequestLog.model_id)
        .order_by(func.count(RequestLog.id).desc())
    )
    model_rows = (await db.execute(model_counts_stmt)).all()
    total_requests = sum(r.cnt for r in model_rows) if model_rows else 0

    model_prefs = []
    for row in model_rows:
        # Resolve display name
        model_result = await db.execute(
            select(Model.display_name, Model.model_id).where(Model.id == row.model_id)
        )
        model_info = model_result.first()
        display = (model_info.display_name or model_info.model_id) if model_info else str(row.model_id)
        pct = round(row.cnt / total_requests * 100, 1) if total_requests else 0
        model_prefs.append({"model_id": str(row.model_id), "display_name": display, "count": row.cnt, "percentage": pct})

    patterns["model_preferences"] = model_prefs

    # -- Time-of-day patterns ---------------------------------------------
    hour_stmt = (
        select(
            extract("hour", RequestLog.created_at).label("hour"),
            func.count(RequestLog.id).label("cnt"),
        )
        .group_by(text("hour"))
        .order_by(text("hour"))
    )
    hour_rows = (await db.execute(hour_stmt)).all()

    hour_dist = {int(r.hour): r.cnt for r in hour_rows} if hour_rows else {}
    peak_hour = max(hour_dist, key=hour_dist.get) if hour_dist else None
    patterns["time_patterns"] = {
        "hourly_distribution": hour_dist,
        "peak_hour": peak_hour,
        "total_requests": total_requests,
    }

    # -- Day-of-week patterns ---------------------------------------------
    dow_stmt = (
        select(
            extract("dow", RequestLog.created_at).label("dow"),
            func.count(RequestLog.id).label("cnt"),
        )
        .group_by(text("dow"))
        .order_by(text("dow"))
    )
    dow_rows = (await db.execute(dow_stmt)).all()

    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    dow_dist = {}
    for r in dow_rows:
        idx = int(r.dow) if r.dow is not None else 0
        dow_dist[day_names[idx % 7]] = r.cnt
    patterns["time_patterns"]["daily_distribution"] = dow_dist

    # -- Session length ---------------------------------------------------
    session_stmt = (
        select(
            func.avg(Conversation.message_count).label("avg_msgs"),
            func.max(Conversation.message_count).label("max_msgs"),
            func.count(Conversation.id).label("total_convos"),
        )
        .where(Conversation.message_count > 0)
    )
    sess = (await db.execute(session_stmt)).first()
    patterns["session_length"] = {
        "average_messages": round(float(sess.avg_msgs), 1) if sess and sess.avg_msgs else 0,
        "max_messages": sess.max_msgs if sess else 0,
        "total_conversations": sess.total_convos if sess else 0,
    }

    # -- Task distribution (persona usage as proxy) -----------------------
    persona_stmt = (
        select(
            RequestLog.persona_id,
            func.count(RequestLog.id).label("cnt"),
        )
        .where(RequestLog.persona_id.isnot(None))
        .group_by(RequestLog.persona_id)
        .order_by(func.count(RequestLog.id).desc())
    )
    persona_rows = (await db.execute(persona_stmt)).all()

    task_dist = []
    for row in persona_rows:
        persona_res = await db.execute(
            select(Persona.name, Persona.description).where(Persona.id == row.persona_id)
        )
        p_info = persona_res.first()
        name = p_info.name if p_info else str(row.persona_id)
        pct = round(row.cnt / total_requests * 100, 1) if total_requests else 0
        task_dist.append({"persona": name, "count": row.cnt, "percentage": pct})

    patterns["task_distribution"] = task_dist

    return {"opted_out": False, "patterns": patterns}


async def get_pattern_suggestions(db: AsyncSession, user_id: str) -> list[dict]:
    """Generate proactive suggestions based on detected usage patterns."""
    if not await _is_pattern_tracking_enabled(db, user_id):
        return []

    data = await detect_usage_patterns(db, user_id)
    if data.get("opted_out"):
        return []

    patterns = data.get("patterns", {})
    suggestions = []

    # Suggestion: dominant model for a task type → recommend a persona
    model_prefs = patterns.get("model_preferences", [])
    task_dist = patterns.get("task_distribution", [])

    if model_prefs and len(model_prefs) >= 2:
        top = model_prefs[0]
        if top["percentage"] >= 60:
            suggestions.append({
                "type": "model_preference",
                "message": f"You use {top['display_name']} for {top['percentage']}% of requests. "
                           f"Consider setting it as your default model.",
                "confidence": round(top["percentage"] / 100, 2),
            })

    # Suggestion: heavy usage without a persona → recommend creating one
    if model_prefs and not task_dist:
        suggestions.append({
            "type": "persona_recommendation",
            "message": "You haven't set up any personas yet. Based on your usage patterns, "
                       "creating a persona could optimize your workflow.",
            "confidence": 0.7,
        })

    # Suggestion: peak-hour insight
    time_pats = patterns.get("time_patterns", {})
    peak = time_pats.get("peak_hour")
    if peak is not None:
        period = "morning" if 5 <= peak < 12 else "afternoon" if 12 <= peak < 17 else "evening" if 17 <= peak < 21 else "night"
        suggestions.append({
            "type": "time_insight",
            "message": f"You're most active in the {period} (peak hour: {peak}:00). ",
            "confidence": 0.8,
        })

    # Suggestion: model per persona pattern
    if len(model_prefs) >= 2 and len(task_dist) >= 2:
        suggestions.append({
            "type": "specialization",
            "message": (
                f"You use multiple models across {len(task_dist)} personas. "
                f"Consider assigning dedicated models to each persona for best results."
            ),
            "confidence": 0.65,
        })

    return suggestions
