"""Agentic event builders and score utilities."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from app.schemas.agentic import AgenticEvent, AgenticRunState, AgenticScore


def build_agentic_event(
    run_id: str,
    state: AgenticRunState,
    actor: str,
    payload: Optional[Dict[str, Any]] = None,
) -> AgenticEvent:
    """Create a normalized agentic event."""

    return AgenticEvent(
        event_id=str(uuid.uuid4()),
        run_id=run_id,
        state=state,
        actor=actor,
        payload=payload or {},
        timestamp=datetime.utcnow().isoformat(),
    )


def compute_agentic_score(events: Iterable[dict]) -> AgenticScore:
    """Compute a basic phase-0 agentic score from emitted events."""

    event_list = list(events)
    has_planning = any(
        e.get("type") == "agentic_event" and e.get("payload", {}).get("state") == AgenticRunState.PLANNING.value
        for e in event_list
    )
    has_execution = any(
        e.get("type") == "agentic_event" and e.get("payload", {}).get("state") == AgenticRunState.EXECUTING.value
        for e in event_list
    )
    has_verification = any(
        e.get("type") == "agentic_event" and e.get("payload", {}).get("state") == AgenticRunState.VERIFYING.value
        for e in event_list
    )
    has_completion = any(
        e.get("type") == "agentic_event" and e.get("payload", {}).get("state") == AgenticRunState.COMPLETED.value
        for e in event_list
    )
    has_approval_outcome = any(
        e.get("type") in {"command_approved", "command_rejected"}
        for e in event_list
    )

    checks = {
        "planning_emitted": has_planning,
        "execution_emitted": has_execution,
        "verification_emitted": has_verification,
        "completion_emitted": has_completion,
        "approval_outcome_recorded": has_approval_outcome,
    }

    score = 0
    score += 25 if has_planning else 0
    score += 25 if has_execution else 0
    score += 25 if has_verification else 0
    score += 25 if has_completion else 0

    missing = [name for name, ok in checks.items() if not ok]

    return AgenticScore(
        score=score,
        checks=checks,
        missing=missing,
        event_count=len(event_list),
    )
