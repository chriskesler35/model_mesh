"""Phase 1-3 agentic pipeline contract tests.

These tests verify the full goal→plan→execute→verify cycle end-to-end
without a live LLM — a fast mock execute_fn proves the orchestration
contracts hold independently of inference providers.

Run with:
    g:/Model_Mesh/backend/venv/Scripts/python.exe -m pytest \
        backend/tests/test_agentic_pipeline.py -q
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any, Dict, List

from app.schemas.agentic import AgenticRunState, AgenticGoal, AgenticPlan
from app.services.agentic_goal import extract_goal
from app.services.agentic_planner import build_plan, summary_for_prompt
from app.services.agentic_verifier import verify_step, verify_plan_completion
from app.services.agentic_orchestrator import AgenticOrchestrator


# ---------------------------------------------------------------------------
# Phase 1 — goal extraction tests
# ---------------------------------------------------------------------------


class TestGoalExtraction:
    def test_build_prompt_sets_objective(self):
        goal = extract_goal("Create a new README for the project", "sess-1")
        assert goal.objective == "Create a new README for the project"

    def test_build_intent_is_build(self):
        goal = extract_goal("build the authentication module", "sess-1")
        assert goal.constraints["intent"] == "build"

    def test_modify_intent(self):
        goal = extract_goal("fix the broken login form", "sess-1")
        assert goal.constraints["intent"] == "modify"

    def test_analysis_intent(self):
        goal = extract_goal("analyze the performance bottlenecks", "sess-1")
        assert goal.constraints["intent"] == "analyze"

    def test_general_intent_fallback(self):
        goal = extract_goal("do the thing", "sess-1")
        assert goal.constraints["intent"] == "general"

    def test_high_risk_goal_sets_requires_approval(self):
        goal = extract_goal("delete all temporary files", "sess-1")
        assert goal.constraints["risk_level"] == "high"
        assert goal.constraints["requires_approval"] is True

    def test_normal_goal_does_not_require_approval(self):
        goal = extract_goal("create a new component", "sess-1")
        assert goal.constraints["requires_approval"] is False

    def test_success_criteria_populated(self):
        goal = extract_goal("build a REST endpoint", "sess-1")
        assert len(goal.success_criteria) >= 1

    def test_extra_constraints_merged(self):
        goal = extract_goal("write tests", "sess-1", extra_constraints={"max_tokens": 1000})
        assert goal.constraints["max_tokens"] == 1000

    def test_goal_id_is_uuid_string(self):
        import uuid
        goal = extract_goal("anything", "sess-1")
        uuid.UUID(goal.goal_id)  # raises if not valid UUID


# ---------------------------------------------------------------------------
# Phase 1 — planner tests
# ---------------------------------------------------------------------------


class TestPlanner:
    def test_plan_has_three_steps(self):
        goal = extract_goal("create a hello world script", "sess-1")
        plan = build_plan(goal)
        assert len(plan.steps) == 3

    def test_step_types_are_analyze_tool_verify(self):
        goal = extract_goal("write a unit test", "sess-1")
        plan = build_plan(goal)
        types = [s.type for s in plan.steps]
        assert types == ["analyze", "tool_call", "verify"]

    def test_dependency_edges_form_linear_chain(self):
        goal = extract_goal("update the config file", "sess-1")
        plan = build_plan(goal)
        step_ids = [s.step_id for s in plan.steps]
        assert plan.dependency_edges[0]["from"] == step_ids[0]
        assert plan.dependency_edges[0]["to"] == step_ids[1]
        assert plan.dependency_edges[1]["from"] == step_ids[1]
        assert plan.dependency_edges[1]["to"] == step_ids[2]

    def test_high_risk_reflected_in_risk_profile(self):
        goal = extract_goal("drop the old database tables", "sess-1")
        plan = build_plan(goal)
        assert plan.risk_profile["requires_approval"] is True

    def test_summary_for_prompt_returns_string(self):
        goal = extract_goal("create api endpoint", "sess-1")
        plan = build_plan(goal)
        summary = summary_for_prompt(plan)
        assert isinstance(summary, str)
        assert "analyze" in summary


# ---------------------------------------------------------------------------
# Phase 3 — verifier tests
# ---------------------------------------------------------------------------


class TestVerifier:
    def test_is_present_check_passes_when_key_exists(self):
        result = verify_step("s1", ["intent_summary is present"], {"intent_summary": "some text"})
        assert result.passed is True

    def test_is_present_check_fails_when_key_missing(self):
        result = verify_step("s1", ["intent_summary is present"], {})
        assert result.passed is False
        assert "intent_summary is present" in result.checks_failed

    def test_without_error_passes_on_success(self):
        result = verify_step("s2", ["action completed without error"], {"success": True})
        assert result.passed is True

    def test_without_error_fails_on_error_key(self):
        result = verify_step("s2", ["action completed without error"], {"error": "something went wrong", "success": False})
        assert result.passed is False

    def test_pass_check_passes(self):
        result = verify_step("s3", ["verification_result pass"], {"verification_result": "pass"})
        assert result.passed is True

    def test_pass_check_fails(self):
        result = verify_step("s3", ["verification_result pass"], {"verification_result": "fail"})
        assert result.passed is False

    def test_verify_plan_completion_all_steps_pass(self):
        goal = extract_goal("build something", "sess-1")
        plan = build_plan(goal)
        step_outputs = {
            s.step_id: {
                "intent_summary": "done",
                "success": True,
                "output": "result",
                "verification_result": "pass",
            }
            for s in plan.steps
        }
        result = verify_plan_completion([s.model_dump() for s in plan.steps], step_outputs)
        assert result["passed"] is True
        assert result["steps_passed"] == 3

    def test_verify_plan_completion_one_step_fails(self):
        goal = extract_goal("build something", "sess-1")
        plan = build_plan(goal)
        step_outputs = {
            plan.steps[0].step_id: {"intent_summary": "ok", "success": True},
            plan.steps[1].step_id: {"error": "failed", "success": False},
            plan.steps[2].step_id: {},
        }
        result = verify_plan_completion([s.model_dump() for s in plan.steps], step_outputs)
        assert result["passed"] is False


# ---------------------------------------------------------------------------
# Phase 2 — orchestrator integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestOrchestratorPipeline:
    async def test_happy_path_reaches_completed(self):
        """Full pipeline: goal→plan→execute→verify → COMPLETED state."""
        emitted: List[Dict[str, Any]] = []

        async def _emit(event_dict):
            emitted.append(event_dict)

        async def _execute_fn(prompt, goal, plan):
            return {
                "success": True,
                "output": "done",
                "intent_summary": "task understood",
                "action_result": "success",
                "verification_result": "pass",
            }

        orch = AgenticOrchestrator("test-session", emit=_emit)
        result = await orch.run("create a test file", _execute_fn, replan_on_failure=False)

        assert result["success"] is True
        assert AgenticRunState.COMPLETED.value in result["state_history"]
        assert AgenticRunState.PLANNING.value in result["state_history"]
        assert AgenticRunState.EXECUTING.value in result["state_history"]
        assert AgenticRunState.VERIFYING.value in result["state_history"]

    async def test_failed_execution_reaches_failed_state(self):
        """Execution failure without replan → FAILED state."""
        emitted: List[str] = []

        async def _emit(event_dict):
            emitted.append(event_dict["state"])

        async def _execute_fn(prompt, goal, plan):
            return {"success": False, "error": "simulated error", "output": ""}

        orch = AgenticOrchestrator("test-session", emit=_emit)
        result = await orch.run("fix the thing", _execute_fn, replan_on_failure=False)

        assert result["success"] is False
        assert AgenticRunState.FAILED.value in result["state_history"]

    async def test_replan_on_failure_attempts_second_execution(self):
        """Verification failure triggers REPLANNING then second EXECUTING."""
        call_count = 0

        async def _execute_fn(prompt, goal, plan):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt: return empty output (will fail checks)
                return {"success": False, "error": "first attempt failed", "output": ""}
            # Second attempt: return success
            return {
                "success": True,
                "output": "done on retry",
                "intent_summary": "done",
                "action_result": "ok",
                "verification_result": "pass",
            }

        orch = AgenticOrchestrator("test-session", emit=None)
        result = await orch.run("create a module", _execute_fn, replan_on_failure=True, max_replan=1)

        assert AgenticRunState.REPLANNING.value in result["state_history"]
        assert call_count == 2

    async def test_high_risk_prompt_includes_awaiting_approval(self):
        """High-risk goal includes AWAITING_APPROVAL in state history."""

        async def _execute_fn(prompt, goal, plan):
            return {
                "success": True,
                "output": "deleted",
                "intent_summary": "ok",
                "action_result": "ok",
                "verification_result": "pass",
            }

        orch = AgenticOrchestrator("test-session", emit=None)
        result = await orch.run("delete the temp directory", _execute_fn, replan_on_failure=False)

        assert AgenticRunState.AWAITING_APPROVAL.value in result["state_history"]

    async def test_events_are_emitted_in_correct_order(self):
        """Events must be emitted in a valid topological order."""
        states: List[str] = []

        async def _emit(event_dict):
            states.append(event_dict["state"])

        async def _execute_fn(prompt, goal, plan):
            return {
                "success": True,
                "output": "done",
                "intent_summary": "understood",
                "action_result": "completed",
                "verification_result": "pass",
            }

        orch = AgenticOrchestrator("test-session", emit=_emit)
        await orch.run("write documentation", _execute_fn, replan_on_failure=False)

        assert states.index("planning") < states.index("executing")
        assert states.index("executing") < states.index("verifying")
        assert states.index("verifying") < states.index("completed")

    async def test_result_contains_agentic_metadata(self):
        """Result dict includes goal_id, plan_id, run_id, state_history."""

        async def _execute_fn(prompt, goal, plan):
            return {"success": True, "output": "ok", "intent_summary": "ok",
                    "action_result": "ok", "verification_result": "pass"}

        orch = AgenticOrchestrator("test-session", emit=None)
        result = await orch.run("analyze the codebase", _execute_fn, replan_on_failure=False)

        assert "run_id" in result
        assert "goal_id" in result
        assert "plan_id" in result
        assert "state_history" in result
        assert len(result["state_history"]) >= 4
