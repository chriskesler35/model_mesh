"""Tests for the agentic run state machine."""

import pytest

from app.schemas.agentic import AgenticRunState
from app.services.agentic_state_machine import AgenticStateMachine


def test_state_machine_happy_path_transitions():
    machine = AgenticStateMachine()

    assert machine.current == AgenticRunState.QUEUED

    machine.transition(AgenticRunState.PLANNING)
    machine.transition(AgenticRunState.EXECUTING)
    machine.transition(AgenticRunState.VERIFYING)
    machine.transition(AgenticRunState.COMPLETED)

    assert machine.current == AgenticRunState.COMPLETED
    assert machine.history == [
        AgenticRunState.QUEUED,
        AgenticRunState.PLANNING,
        AgenticRunState.EXECUTING,
        AgenticRunState.VERIFYING,
        AgenticRunState.COMPLETED,
    ]


def test_state_machine_rejects_invalid_transition():
    machine = AgenticStateMachine()

    with pytest.raises(ValueError):
        machine.transition(AgenticRunState.COMPLETED)


def test_state_machine_allows_terminal_stability():
    machine = AgenticStateMachine()

    machine.transition(AgenticRunState.PLANNING)
    machine.transition(AgenticRunState.FAILED)

    # Re-applying the same terminal state should be a no-op.
    machine.transition(AgenticRunState.FAILED)
    assert machine.current == AgenticRunState.FAILED
