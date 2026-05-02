"""Phase 2 — Agentic Orchestrator.

Drives an arbitrary async execution function through the canonical
goal → plan → execute → verify state machine cycle.

Usage::

    orchestrator = AgenticOrchestrator(session_id, emit_event_fn)
    result = await orchestrator.run(prompt, execute_fn)

``execute_fn`` must have the signature::

    async def execute_fn(
        prompt: str,
        goal: AgenticGoal,
        plan: AgenticPlan,
    ) -> dict:
        ...

The return dict should contain at minimum:
    - ``success`` (bool)
    - ``output`` (str) — final answer or artefact description
    - ``error`` (str, optional) — non-empty on failure

The orchestrator handles the full lifecycle including optional re-planning
on verification failure and approval gates for high-risk goals.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.schemas.agentic import AgenticGoal, AgenticPlan, AgenticRunState
from app.services.agentic_events import build_agentic_event
from app.services.agentic_state_machine import AgenticStateMachine
from app.services.agentic_goal import extract_goal
from app.services.agentic_planner import build_plan, summary_for_prompt
from app.services.agentic_verifier import verify_plan_completion

logger = logging.getLogger(__name__)

# Type alias for the async event callback
EventCallback = Callable[[Dict[str, Any]], Awaitable[None]]

# Type alias for the execution function
ExecuteFn = Callable[
    [str, AgenticGoal, AgenticPlan],
    Awaitable[Dict[str, Any]],
]


class AgenticOrchestrator:
    """Drives execution through the unified agentic state machine.

    The orchestrator is intentionally execution-agnostic — it delegates
    the actual work to the provided ``execute_fn``, which can be an
    AgentRunner, a simple LLM call, or any other async callable.

    Parameters
    ----------
    session_id:
        Workbench session that owns this orchestrator instance.
    emit:
        Optional async callback invoked on every state transition with the
        serialised AgenticEvent dict.  Wire this to the SSE push helper in
        workbench.py to get live telemetry.
    """

    def __init__(
        self,
        session_id: str,
        emit: Optional[EventCallback] = None,
    ) -> None:
        self.session_id = session_id
        self.run_id = str(uuid.uuid4())
        self.sm = AgenticStateMachine()
        self._emit = emit

        self.goal: Optional[AgenticGoal] = None
        self.plan: Optional[AgenticPlan] = None
        self.step_outputs: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _push(
        self,
        state: AgenticRunState,
        actor: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Transition state machine and emit a telemetry event."""
        self.sm.transition(state)
        event = build_agentic_event(self.run_id, state, actor, payload or {})
        if self._emit:
            try:
                await self._emit(event.model_dump())
            except Exception as exc:  # pragma: no cover
                logger.warning("Event emit failed: %s", exc)
        logger.debug("Agentic [%s] %s → %s", self.run_id[:8], actor, state.value)

    def _record_step_outputs(self, result: Dict[str, Any]) -> None:
        """Map execution result to each plan step's output slot."""
        if self.plan is None:
            return
        for step in self.plan.steps:
            # All steps share the same execution output for the baseline plan.
            # A future multi-step planner will route individual outputs.
            self.step_outputs[step.step_id] = result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state_history(self) -> List[str]:
        """Ordered list of state names visited so far."""
        return [s.value for s in self.sm.history]

    async def run(
        self,
        prompt: str,
        execute_fn: ExecuteFn,
        *,
        allowed_tools: Optional[List[str]] = None,
        blocked_tools: Optional[List[str]] = None,
        replan_on_failure: bool = True,
        max_replan: int = 1,
    ) -> Dict[str, Any]:
        """Execute the full goal → plan → execute → verify cycle.

        Parameters
        ----------
        prompt:
            Raw user task string.
        execute_fn:
            Async callable ``(prompt, goal, plan) → result_dict``.
        allowed_tools / blocked_tools:
            Forwarded to goal extraction.
        replan_on_failure:
            If True, attempt one re-plan when verification fails.
        max_replan:
            Maximum number of re-plan attempts.

        Returns
        -------
        dict with keys:
            ``run_id``, ``goal_id``, ``plan_id``, ``result``,
            ``verification``, ``state_history``, ``success``.
        """
        # ── PLANNING ──────────────────────────────────────────────────
        await self._push(
            AgenticRunState.PLANNING,
            "orchestrator",
            {"prompt_length": len(prompt), "session_id": self.session_id},
        )

        self.goal = extract_goal(
            prompt,
            self.session_id,
            allowed_tools=allowed_tools,
            blocked_tools=blocked_tools,
        )
        self.plan = build_plan(self.goal)

        # ── AWAITING_APPROVAL (high-risk goals only) ──────────────────
        if self.goal.constraints.get("requires_approval", False):
            await self._push(
                AgenticRunState.AWAITING_APPROVAL,
                "orchestrator",
                {
                    "reason": "high-risk goal detected",
                    "goal_id": self.goal.goal_id,
                    "risk_level": self.goal.constraints.get("risk_level"),
                },
            )

        execute_result: Dict[str, Any] = {}
        replan_count = 0

        while True:
            # ── EXECUTING ─────────────────────────────────────────────
            await self._push(
                AgenticRunState.EXECUTING,
                "orchestrator",
                {
                    "plan_id": self.plan.plan_id,
                    "step_count": len(self.plan.steps),
                    "replan_attempt": replan_count,
                    "plan_summary": summary_for_prompt(self.plan),
                },
            )

            try:
                execute_result = await execute_fn(prompt, self.goal, self.plan)
            except Exception as exc:
                logger.error("Execution error in orchestrator: %s", exc)
                execute_result = {
                    "error": str(exc),
                    "success": False,
                    "output": "",
                }

            self._record_step_outputs(execute_result)

            # ── VERIFYING ─────────────────────────────────────────────
            await self._push(
                AgenticRunState.VERIFYING,
                "verifier",
                {"plan_id": self.plan.plan_id, "step_outputs_count": len(self.step_outputs)},
            )

            verification = verify_plan_completion(
                [s.model_dump() for s in self.plan.steps],
                self.step_outputs,
            )

            if verification["passed"]:
                # ── COMPLETED ─────────────────────────────────────────
                await self._push(
                    AgenticRunState.COMPLETED,
                    "orchestrator",
                    {"goal_id": self.goal.goal_id, "verification": verification},
                )
                return {
                    "run_id": self.run_id,
                    "goal_id": self.goal.goal_id,
                    "plan_id": self.plan.plan_id,
                    "result": execute_result,
                    "verification": verification,
                    "state_history": self.state_history,
                    "success": True,
                }

            # ── Decide replan or fail ──────────────────────────────────
            if replan_on_failure and replan_count < max_replan:
                replan_count += 1
                failed_checks = [
                    r["checks_failed"]
                    for r in verification.get("step_results", [])
                    if r.get("checks_failed")
                ]
                await self._push(
                    AgenticRunState.REPLANNING,
                    "orchestrator",
                    {
                        "reason": "verification_failed",
                        "attempt": replan_count,
                        "failed_checks": failed_checks,
                    },
                )
                # Rebuild plan for the same goal
                self.plan = build_plan(self.goal)
                self.step_outputs = {}
                # Loop → EXECUTING again
            else:
                # ── FAILED ────────────────────────────────────────────
                await self._push(
                    AgenticRunState.FAILED,
                    "orchestrator",
                    {"goal_id": self.goal.goal_id, "verification": verification},
                )
                return {
                    "run_id": self.run_id,
                    "goal_id": self.goal.goal_id,
                    "plan_id": self.plan.plan_id,
                    "result": execute_result,
                    "verification": verification,
                    "state_history": self.state_history,
                    "success": False,
                }
