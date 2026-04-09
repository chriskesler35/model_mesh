"""Workflow trigger detection and pipeline creation from chat messages.

Detects when a user message matches trigger_keywords from any method
(built-in or custom), suggests running a pipeline, and handles confirmation.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.custom_method import CustomMethod

logger = logging.getLogger(__name__)

# ── Built-in method trigger keywords ─────────────────────────────────────────
# Built-in methods don't store trigger_keywords in the DB, so we define them here.
_BUILTIN_TRIGGERS: dict[str, list[str]] = {
    "bmad": [
        "build", "create", "develop", "application", "app", "website",
        "landing page", "product", "project", "full stack", "saas",
        "platform", "system", "architecture", "design",
    ],
    "gsd": [
        "quick", "prototype", "hack", "script", "fast", "simple",
        "just make", "quickly", "rapid", "experiment", "spike",
    ],
    "superpowers": [
        "research", "analyze", "investigate", "compare", "deep dive",
        "comprehensive", "evaluate", "study", "assessment", "review",
    ],
}

# Minimum word-overlap ratio to consider a match
_MATCH_THRESHOLD = 0.15


def _tokenize(text: str) -> set[str]:
    """Lowercase and split text into word tokens."""
    return set(re.findall(r"[a-z]+", text.lower()))


def _score_overlap(message_tokens: set[str], keywords: list[str]) -> float:
    """Compute simple word-overlap score between message and keyword list.

    For multi-word keywords (e.g. "landing page"), checks if all words
    appear in the message. Returns ratio of matched keywords to total.
    """
    if not keywords:
        return 0.0
    matched = 0
    for kw in keywords:
        kw_words = set(kw.lower().split())
        if kw_words.issubset(message_tokens):
            matched += 1
    return matched / len(keywords)


async def detect_workflow_trigger(
    message: str, db: AsyncSession
) -> Optional[dict]:
    """Match user message against all method trigger_keywords.

    Returns:
        None if no trigger matches.
        dict with {method_id, method_name, score, is_custom} for the best match.
    """
    tokens = _tokenize(message)
    if len(tokens) < 3:
        return None  # Too short to be a workflow request

    best: Optional[dict] = None
    best_score = 0.0

    # Check built-in methods
    for method_id, keywords in _BUILTIN_TRIGGERS.items():
        score = _score_overlap(tokens, keywords)
        if score > best_score and score >= _MATCH_THRESHOLD:
            best_score = score
            best = {
                "method_id": method_id,
                "method_name": method_id.upper(),
                "score": round(score, 3),
                "is_custom": False,
            }

    # Check custom methods from DB
    result = await db.execute(
        select(CustomMethod).where(CustomMethod.is_active == True)
    )
    for cm in result.scalars().all():
        keywords = cm.trigger_keywords or []
        if not keywords:
            continue
        score = _score_overlap(tokens, keywords)
        if score > best_score and score >= _MATCH_THRESHOLD:
            best_score = score
            best = {
                "method_id": cm.id,
                "method_name": cm.name,
                "score": round(score, 3),
                "is_custom": True,
            }

    return best


async def handle_workflow_trigger(
    message: str,
    match: dict,
    db: AsyncSession,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Return a suggestion response for a detected workflow trigger.

    The user must confirm before the pipeline is actually created.
    """
    method_name = match["method_name"]
    method_id = match["method_id"]
    return (
        f"I can run the **{method_name}** pipeline for this. "
        f"Shall I proceed?\n\n"
        f"Reply **yes** to start the pipeline, or continue chatting normally.\n\n"
        f"_Matched method: `{method_id}` (score: {match['score']})_"
    )


async def handle_confirm_workflow(
    params: dict,
    db: AsyncSession,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Create a pipeline after user confirms a workflow trigger.

    Expects params with: method_id, task, session_id.
    """
    method_id = params.get("method_id", "")
    task = params.get("task", "")
    session_id = params.get("session_id", "")

    if not session_id:
        return (
            "No active workbench session found. "
            "Please open a workbench session first, then try again."
        )

    if not method_id:
        return "No method specified. Please try describing your task again."

    # Create pipeline via the existing pipeline creation logic
    from app.routes.pipelines import create_pipeline, PipelineCreate

    try:
        body = PipelineCreate(
            session_id=session_id,
            method_id=method_id,
            task=task,
            auto_approve=False,
        )
        result = await create_pipeline(body, db)
        pipeline_id = result.get("id", "unknown")
        method_name = result.get("method_id", method_id)
        status = result.get("status", "pending")
        return (
            f"Pipeline started.\n\n"
            f"- **Pipeline ID:** `{pipeline_id}`\n"
            f"- **Method:** {method_name}\n"
            f"- **Status:** {status}\n"
            f"- **Task:** {task}\n\n"
            f"Switch to the **Pipeline** view to monitor progress, "
            f"or I'll post status updates here as phases complete."
        )
    except Exception as e:
        logger.error(f"Failed to create pipeline: {e}", exc_info=True)
        return f"Failed to start pipeline: {str(e)}"


async def handle_suggest_pipeline(
    message: str,
    db: AsyncSession,
    *,
    conversation_id: Optional[str] = None,
) -> Optional[str]:
    """For complex-looking messages with no trigger match, suggest a pipeline.

    Returns None if the message doesn't look complex enough.
    """
    tokens = _tokenize(message)
    # Heuristic: message with 15+ words and action-oriented language
    complexity_markers = {
        "build", "create", "develop", "implement", "design", "generate",
        "write", "make", "set up", "deploy", "integrate", "migrate",
        "refactor", "optimize", "test", "automate",
    }
    action_count = len(tokens & complexity_markers)
    if len(tokens) >= 15 and action_count >= 1:
        return (
            "This seems like a complex task. "
            "Want me to run it as a **pipeline** for a more structured approach?\n\n"
            "Reply **yes** or tell me which method to use "
            "(e.g., **BMAD**, **GSD**, **SuperPowers**)."
        )
    return None
