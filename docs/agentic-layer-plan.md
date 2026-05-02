# Agentic Layer Plan

## Objective

Ensure DevForgeAI demonstrates true agentic behavior after a user request is submitted: goal decomposition, iterative execution, tool use, stateful memory, policy-constrained autonomy, self-verification, and transparent human oversight.

This plan treats the Agentic Layer as a first-class orchestration subsystem above model routing and below UI/API surfaces.

## Current Baseline (What Already Exists)

Current capabilities already present in the codebase:

- Iterative tool loop in agent runner.
- Command safety tiers (auto, notice, approval, blocked).
- Single-agent workbench orchestration with SSE telemetry.
- Multi-agent phase pipelines with approval gates and retries.
- Persona and model resolution with fallback routing.
- Session and agent memory persistence.

Current weakness is not missing primitives; it is missing one unified contract that guarantees agentic behavior consistently across chat, workbench, and pipelines.

## Definition Of TRUE Agentic AI For This Product

For DevForgeAI, a run is considered truly agentic only if all criteria below are met:

1. Goal understanding: the system can derive an explicit objective and constraints from user input.
2. Plan synthesis: the system can generate a structured plan with dependencies and stop conditions.
3. Iterative execution: the system runs plan steps with tool calls and state updates, not one-shot text output.
4. Reflection loop: the system evaluates progress after each step and can re-plan on failure.
5. Policy compliance: the system enforces command and data safety policies at runtime.
6. Human control: the user can inspect, approve, reject, pause, resume, and override.
7. Traceability: each decision and action is captured as machine-readable run telemetry.
8. Verification: the system performs explicit success checks against expected outcomes.

## Target Agentic Layer Architecture

### Layer Position

The Agentic Layer will sit between request entry points and execution engines.

- Entry points: chat, workbench session starts, pipeline starts.
- Execution engines: command executor, tool adapters, pipeline phase executor.

### Core Components

1. Intent and Goal Contract
- Converts user prompt to a typed goal object.
- Extracts constraints: scope, risk tolerance, cost cap, latency target, approval mode.

2. Planner
- Builds a step graph (DAG) from goal object.
- Tags each step with required tools, risk tier, expected outputs, and verification checks.

3. Runtime Orchestrator
- Executes step graph iteratively.
- Handles retries, backoff, re-planning, and partial completion.
- Maintains explicit run state machine.

4. Policy and Guardrail Engine
- Evaluates each step pre-execution.
- Enforces command, network, filesystem, and data egress policies.
- Emits approval-required events for high-risk actions.

5. Reflection and Verifier
- After each step: compare observed output vs expected outcome.
- On mismatch: classify failure type and choose retry, alternative path, or escalation.

6. Memory and Context Manager
- Builds layered context (session, project, user, repository).
- Adds retrieval and summarization budget controls.

7. Telemetry and Audit Bus
- Standard event schema for all runs.
- Enables replay, debugging, quality scoring, and compliance auditing.

### Unified Run State Machine

Proposed states:

- queued
- planning
- awaiting_approval
- executing
- verifying
- replanning
- completed
- failed
- cancelled

State changes must be streamed over SSE and stored in persistent run history.

## Data Contracts To Introduce

1. AgenticGoal
- goal_id
- objective
- constraints
- success_criteria
- allowed_tools
- blocked_tools

2. AgenticPlan
- plan_id
- steps[]
- dependency_edges[]
- risk_profile
- estimated_cost

3. AgenticStep
- step_id
- type (analyze, tool_call, code_edit, verify, summarize)
- inputs
- expected_outputs
- verification_checks[]
- status

4. AgenticEvent
- event_id
- run_id
- state
- actor (planner, orchestrator, verifier, policy)
- payload
- timestamp

## Execution Policy Model

Policy should be explicit and configurable at project/session/user levels.

Policy dimensions:

- Tool allow/deny lists
- Command tier behavior
- Approval thresholds
- Max retries per step
- Max cumulative run duration
- Max model cost per run
- External network permissions

Policy precedence:

- Global default
- Project override
- Session override
- Per-step strict override

## Quality Gates (Agentic Acceptance)

A run passes agentic acceptance only if:

1. Plan exists and includes at least one verification step.
2. At least one execution action is taken (tool or command) when action is required.
3. Verification emits pass/fail signal.
4. Any high-risk action records explicit approval result.
5. Full event trail is replayable.

## Phased Rollout

### Phase 0 - Contract And Observability Foundation

Scope:

- Add shared schemas for goal, plan, step, event.
- Add unified run state machine and event taxonomy.
- Add Agentic Score (0-100) per run based on acceptance criteria.

Deliverables:

- backend/app/schemas/agentic.py
- backend/app/services/agentic_events.py
- backend/app/services/agentic_state_machine.py
- SSE event updates for workbench and pipeline streams.

### Phase 1 - Planner And Goal Extraction

Scope:

- Build goal extraction from incoming requests.
- Add planner service that produces executable step graph.

Deliverables:

- backend/app/services/agentic_goal.py
- backend/app/services/agentic_planner.py
- planner invocation in workbench and pipeline create flows.

### Phase 2 - Runtime Orchestrator Integration

Scope:

- Move iterative logic behind a unified orchestrator wrapper.
- Add reflection and re-plan branch.

Deliverables:

- backend/app/services/agentic_orchestrator.py
- Integration adapters for existing agent_runner and pipeline executor.

### Phase 3 - Verification Layer And Regression Harness

Scope:

- Add verifier service with deterministic checks where possible.
- Add acceptance regression tests for agentic contracts.

Deliverables:

- backend/app/services/agentic_verifier.py
- tests/test_agentic_contracts.py
- tests/e2e/specs/12-agentic-run-contract.spec.ts

### Phase 4 - UX For Human-In-The-Loop Control

Scope:

- Add UI for goal-plan-step inspection.
- Add controls: approve, reject, retry-step, re-plan.

Deliverables:

- Workbench run graph panel.
- Pipeline phase detail with step-level verification evidence.

## Immediate Build Sequence (Start Now)

1. Implement Phase 0 schemas and event model first.
2. Instrument workbench run loop to emit state transitions.
3. Instrument pipelines to emit the same schema.
4. Add an initial Agentic Score endpoint for recent runs.
5. Add backend tests that assert state transitions and event completeness.

## Non-Goals For Initial Rollout

- Full autonomous execution without any approval gates.
- Replacing existing command safety model.
- Rewriting all route handlers at once.

## Risks And Mitigations

Risk: Event schema drift across workbench and pipeline flows.
Mitigation: One shared event builder module and strict typed schema validation.

Risk: Cost and latency increase due to extra planning/reflection calls.
Mitigation: planner budget limits, cached plans, and model tiering.

Risk: Over-automation creates unsafe behavior.
Mitigation: keep approval gates, enforce policy precedence, add dry-run mode.

## Success Metrics

1. Agentic Score average >= 85 for workbench and pipeline runs.
2. 100 percent of high-risk actions include approval outcome.
3. 100 percent of completed runs include verification event.
4. Mean time to diagnose failed run reduced by >= 50 percent.

## Decision Needed Before Implementation

Choose default autonomy profile for new runs:

- Conservative: approvals required for all non-trivial mutations.
- Balanced: approvals only for tier-3/high-risk actions.
- Aggressive: approvals minimized, with post-action audit.

Recommended default: Balanced.
