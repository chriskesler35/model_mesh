"""Tests for agentic event shaping and score computation."""

from app.schemas.agentic import AgenticRunState
from app.services.agentic_events import build_agentic_event, compute_agentic_score


def test_build_agentic_event_contract():
    event = build_agentic_event(
        run_id="run-123",
        state=AgenticRunState.EXECUTING,
        actor="orchestrator",
        payload={"step": "tool_call"},
    )

    dumped = event.model_dump()
    assert dumped["run_id"] == "run-123"
    assert dumped["state"] == AgenticRunState.EXECUTING
    assert dumped["actor"] == "orchestrator"
    assert dumped["payload"]["step"] == "tool_call"
    assert isinstance(dumped["event_id"], str) and dumped["event_id"]
    assert isinstance(dumped["timestamp"], str) and dumped["timestamp"]


def test_compute_agentic_score_baseline():
    events = [
        {
            "type": "agentic_event",
            "payload": {
                "state": AgenticRunState.PLANNING.value,
            },
        },
        {
            "type": "agentic_event",
            "payload": {
                "state": AgenticRunState.EXECUTING.value,
            },
        },
        {
            "type": "agentic_event",
            "payload": {
                "state": AgenticRunState.VERIFYING.value,
            },
        },
        {
            "type": "agentic_event",
            "payload": {
                "state": AgenticRunState.COMPLETED.value,
            },
        },
        {
            "type": "command_approved",
            "payload": {"command_id": "abc"},
        },
    ]

    score = compute_agentic_score(events)

    assert score.score == 100
    assert score.missing == []
    assert score.checks["planning_emitted"] is True
    assert score.checks["execution_emitted"] is True
    assert score.checks["verification_emitted"] is True
    assert score.checks["completion_emitted"] is True
    assert score.checks["approval_outcome_recorded"] is True
