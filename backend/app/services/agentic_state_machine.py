"""State machine for canonical agentic run transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set

from app.schemas.agentic import AgenticRunState


VALID_TRANSITIONS: Dict[AgenticRunState, Set[AgenticRunState]] = {
    AgenticRunState.QUEUED: {
        AgenticRunState.PLANNING,
        AgenticRunState.CANCELLED,
        AgenticRunState.FAILED,
    },
    AgenticRunState.PLANNING: {
        AgenticRunState.EXECUTING,
        AgenticRunState.AWAITING_APPROVAL,
        AgenticRunState.REPLANNING,
        AgenticRunState.CANCELLED,
        AgenticRunState.FAILED,
    },
    AgenticRunState.AWAITING_APPROVAL: {
        AgenticRunState.EXECUTING,
        AgenticRunState.CANCELLED,
        AgenticRunState.FAILED,
    },
    AgenticRunState.EXECUTING: {
        AgenticRunState.VERIFYING,
        AgenticRunState.AWAITING_APPROVAL,
        AgenticRunState.REPLANNING,
        AgenticRunState.CANCELLED,
        AgenticRunState.FAILED,
    },
    AgenticRunState.VERIFYING: {
        AgenticRunState.COMPLETED,
        AgenticRunState.REPLANNING,
        AgenticRunState.FAILED,
        AgenticRunState.CANCELLED,
    },
    AgenticRunState.REPLANNING: {
        AgenticRunState.EXECUTING,
        AgenticRunState.AWAITING_APPROVAL,
        AgenticRunState.FAILED,
        AgenticRunState.CANCELLED,
    },
    AgenticRunState.COMPLETED: set(),
    AgenticRunState.FAILED: set(),
    AgenticRunState.CANCELLED: set(),
}


@dataclass
class AgenticStateMachine:
    """Simple in-memory state machine for agentic orchestration."""

    current: AgenticRunState = AgenticRunState.QUEUED
    history: list[AgenticRunState] = field(default_factory=lambda: [AgenticRunState.QUEUED])

    def can_transition(self, next_state: AgenticRunState) -> bool:
        if next_state == self.current:
            return True
        return next_state in VALID_TRANSITIONS[self.current]

    def transition(self, next_state: AgenticRunState) -> AgenticRunState:
        if not self.can_transition(next_state):
            raise ValueError(f"Invalid transition: {self.current.value} -> {next_state.value}")
        if next_state != self.current:
            self.current = next_state
            self.history.append(next_state)
        return self.current
