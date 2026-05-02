"""Agentic layer schemas for run contracts and telemetry."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgenticRunState(str, Enum):
    """Canonical run states for agentic orchestration."""

    QUEUED = "queued"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgenticGoal(BaseModel):
    """Typed goal contract extracted from a user request."""

    goal_id: str
    objective: str
    constraints: Dict[str, Any] = Field(default_factory=dict)
    success_criteria: List[str] = Field(default_factory=list)
    allowed_tools: List[str] = Field(default_factory=list)
    blocked_tools: List[str] = Field(default_factory=list)


class AgenticStep(BaseModel):
    """A single executable step in an agentic plan."""

    step_id: str
    type: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_outputs: Dict[str, Any] = Field(default_factory=dict)
    verification_checks: List[str] = Field(default_factory=list)
    status: str = "pending"


class AgenticPlan(BaseModel):
    """Plan contract for orchestration."""

    plan_id: str
    steps: List[AgenticStep] = Field(default_factory=list)
    dependency_edges: List[Dict[str, str]] = Field(default_factory=list)
    risk_profile: Dict[str, Any] = Field(default_factory=dict)
    estimated_cost: Optional[float] = None


class AgenticEvent(BaseModel):
    """Structured run telemetry event."""

    event_id: str
    run_id: str
    state: AgenticRunState
    actor: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class AgenticScore(BaseModel):
    """Agentic quality score for a run/session."""

    score: int
    checks: Dict[str, bool] = Field(default_factory=dict)
    missing: List[str] = Field(default_factory=list)
    event_count: int = 0
