"""Phase 1 — Agentic Planner.

Converts a typed AgenticGoal into an executable AgenticPlan (step graph).
This baseline implementation produces a deterministic three-step linear plan:

    understand → execute → verify

A future iteration will use an LLM call with structured output to produce
branching DAGs for multi-objective goals.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

from app.schemas.agentic import AgenticGoal, AgenticPlan, AgenticStep


def build_plan(goal: AgenticGoal) -> AgenticPlan:
    """Build a baseline AgenticPlan from a typed goal.

    The plan always contains exactly three steps:

    1. **understand** — analyse the objective, extract constraints, enumerate
       sub-tasks.  Produces an ``intent_summary`` used downstream.
    2. **execute** — carry out the primary action described in the objective.
       Produces an ``action_result``.
    3. **verify** — check that all success criteria from the goal are satisfied.
       Produces a ``verification_result`` of ``"pass"`` or ``"fail"``.

    Parameters
    ----------
    goal:
        Typed goal from :func:`~app.services.agentic_goal.extract_goal`.

    Returns
    -------
    AgenticPlan
        Fully-formed plan contract ready for the orchestrator.
    """
    understand_step = AgenticStep(
        step_id=str(uuid.uuid4()),
        type="analyze",
        inputs={
            "objective": goal.objective,
            "intent": goal.constraints.get("intent", "general"),
            "risk_level": goal.constraints.get("risk_level", "normal"),
        },
        expected_outputs={"intent_summary": "non-empty string"},
        verification_checks=["intent_summary is present"],
        status="pending",
    )

    execute_step = AgenticStep(
        step_id=str(uuid.uuid4()),
        type="tool_call",
        inputs={
            "goal_id": goal.goal_id,
            "allowed_tools": goal.allowed_tools,
            "blocked_tools": goal.blocked_tools,
        },
        expected_outputs={"action_result": "any"},
        verification_checks=["action completed without error"],
        status="pending",
    )

    verify_step = AgenticStep(
        step_id=str(uuid.uuid4()),
        type="verify",
        inputs={
            "success_criteria": goal.success_criteria,
            "goal_id": goal.goal_id,
        },
        expected_outputs={"verification_result": "pass"},
        verification_checks=list(goal.success_criteria),
        status="pending",
    )

    has_risk = goal.constraints.get("risk_level") == "high"
    steps = [understand_step, execute_step, verify_step]

    return AgenticPlan(
        plan_id=str(uuid.uuid4()),
        steps=steps,
        dependency_edges=[
            {"from": understand_step.step_id, "to": execute_step.step_id},
            {"from": execute_step.step_id, "to": verify_step.step_id},
        ],
        risk_profile={
            "requires_approval": has_risk,
            "risk_level": goal.constraints.get("risk_level", "normal"),
            "step_count": len(steps),
        },
        estimated_cost=None,
    )


def summary_for_prompt(plan: AgenticPlan) -> str:
    """Return a human-readable plan summary for injecting into the LLM context."""
    lines: list[str] = [f"Plan {plan.plan_id[:8]} — {len(plan.steps)} steps:"]
    for i, step in enumerate(plan.steps, 1):
        lines.append(
            f"  {i}. [{step.type}] inputs={list(step.inputs.keys())} "
            f"checks={step.verification_checks}"
        )
    return "\n".join(lines)
