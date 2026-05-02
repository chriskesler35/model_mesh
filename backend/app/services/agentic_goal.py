"""Phase 1 — Goal Extraction.

Converts a raw user prompt into a typed AgenticGoal. This lightweight
heuristic extractor avoids an extra LLM round-trip while still producing
structured, contractually valid goal objects.  A future phase may optionally
use a fast model with structured-output to handle ambiguous multi-intent
prompts with higher fidelity.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.schemas.agentic import AgenticGoal

# ---------------------------------------------------------------------------
# Keyword sets used for heuristic classification
# ---------------------------------------------------------------------------

_RISK_KEYWORDS: frozenset[str] = frozenset(
    {"delete", "drop", "rm", "remove", "format", "wipe", "destroy", "truncate", "purge"}
)

_BUILD_KEYWORDS: frozenset[str] = frozenset(
    {"create", "build", "implement", "add", "write", "generate", "scaffold", "make"}
)

_MODIFY_KEYWORDS: frozenset[str] = frozenset(
    {"fix", "update", "refactor", "patch", "change", "edit", "improve", "migrate", "rename"}
)

_ANALYSIS_KEYWORDS: frozenset[str] = frozenset(
    {
        "analyze", "explain", "review", "summarize", "check", "describe",
        "list", "find", "search", "audit", "verify", "inspect",
    }
)


def extract_goal(
    prompt: str,
    session_id: str,
    *,
    allowed_tools: Optional[List[str]] = None,
    blocked_tools: Optional[List[str]] = None,
    extra_constraints: Optional[Dict[str, Any]] = None,
) -> AgenticGoal:
    """Extract a typed AgenticGoal from a user prompt.

    Parameters
    ----------
    prompt:
        The raw user task string.
    session_id:
        The workbench session that owns this goal.
    allowed_tools:
        Explicit tool allowlist (empty = unrestricted).
    blocked_tools:
        Explicit tool blocklist (empty = none blocked beyond global policy).
    extra_constraints:
        Additional key-value pairs merged into the constraints dict.

    Returns
    -------
    AgenticGoal
        Typed goal contract ready for the planner.
    """
    words = set(prompt.lower().split())

    # ------------------------------------------------------------------
    # Derive intent category
    # ------------------------------------------------------------------
    is_build = bool(words & _BUILD_KEYWORDS)
    is_modify = bool(words & _MODIFY_KEYWORDS)
    is_analysis = bool(words & _ANALYSIS_KEYWORDS)
    has_risk = bool(words & _RISK_KEYWORDS)

    # ------------------------------------------------------------------
    # Derive success criteria
    # ------------------------------------------------------------------
    success_criteria: List[str] = []

    if is_build:
        success_criteria.append("target artifact exists and is functional")
    if is_modify:
        success_criteria.append("modification applied without breaking existing behaviour")
    if is_analysis:
        success_criteria.append("analysis output is complete and non-empty")
    if not success_criteria:
        success_criteria.append("task completed without errors")

    # ------------------------------------------------------------------
    # Build constraints dict
    # ------------------------------------------------------------------
    constraints: Dict[str, Any] = {
        "session_id": session_id,
        "risk_level": "high" if has_risk else "normal",
        "requires_approval": has_risk,
        "intent": (
            "build" if is_build
            else "modify" if is_modify
            else "analyze" if is_analysis
            else "general"
        ),
    }
    if extra_constraints:
        constraints.update(extra_constraints)

    return AgenticGoal(
        goal_id=str(uuid.uuid4()),
        objective=prompt.strip(),
        constraints=constraints,
        success_criteria=success_criteria,
        allowed_tools=allowed_tools or [],
        blocked_tools=blocked_tools or [],
    )
