# DevForgeAI / AgentMesh — Epics & Stories

> **Created:** 2026-04-08
> **Source:** DEVFORGEAI_SPEC.md, CHARTER.md, project-context.md, codebase audit
> **Scope:** All remaining work (Phase 2.0 gaps + Phase 3.0+ backlog)
> **Status:** Implementation-ready

---

## Quick Reference

| # | Epic | Stories | Status |
|---|------|---------|--------|
| E1 | Agent Direct Execution | 5 | Not Started |
| E2 | Pipeline Parallel Execution | 5 | Not Started |
| E3 | Conditional Workflow Branching | 4 | Not Started |
| E4 | Visual Workflow Builder | 6 | Not Started |
| E5 | Custom Workflow Templates | 4 | Not Started |
| E6 | Enhanced Analytics Dashboard | 5 | Not Started |
| E7 | OAuth & Advanced Auth | 5 | Partial (JWT exists) |
| E8 | Real-time Collaboration | 5 | Partial (handoff exists) |
| E9 | Voice Interface | 5 | Not Started |
| E10 | Production Deployment | 5 | Partial (Docker exists) |
| E11 | Chat Self-Modification | 4 | Not Started |
| E12 | Advanced Learning & Personalization | 4 | Not Started |
| **Total** | | **57** | |

---

## Epic 1: Agent Direct Execution

**Goal:** Enable running a single agent directly via API, with iterative tool use and memory, outside of the pipeline/workflow context.

**Spec Reference:** DEVFORGEAI_SPEC.md Section 7.1 — `POST /v1/agents/{id}/run`

**Current State:** Agent CRUD exists (`backend/app/routes/agents.py`). Tool execution exists (`backend/app/services/command_executor.py`). But there is no endpoint to run an agent as a standalone task. Today, agents only execute within pipelines.

---

### Story 1.1: Agent Run Endpoint

**As a** user, **I want to** POST a task to `/v1/agents/{agent_id}/run` **so that** I can execute a single agent without creating a full pipeline.

**Acceptance Criteria:**
- [ ] `POST /v1/agents/{agent_id}/run` accepts `{ task: string, context?: object, stream?: boolean }`
- [ ] Resolves the agent's model via persona chain (agent.persona_id → persona.primary_model_id → fallback)
- [ ] If `stream: true`, returns SSE event stream; otherwise returns completed result as JSON
- [ ] Response includes: `{ run_id, agent_id, status, output, tokens_used, duration_ms }`
- [ ] Creates a `request_log` entry for cost tracking
- [ ] Returns 404 if agent not found, 422 if task is empty

**Technical Notes:**
- File: `backend/app/routes/agents.py` — add new endpoint after line 370
- Reuse `model_client.py` for LLM calls
- Reuse `phase_templates.py` pattern for system prompt injection
- Schema: create `AgentRunRequest` / `AgentRunResponse` in `backend/app/schemas/agents.py`

**Complexity:** Medium

---

### Story 1.2: Agent Iterative Tool Loop

**As a** user, **I want** the agent to iteratively call tools (read_file, write_file, shell_execute, http_request) **so that** it can complete multi-step tasks autonomously.

**Acceptance Criteria:**
- [ ] Agent run loops up to `agent.max_iterations` times
- [ ] Each iteration: send LLM call → parse output for tool commands → execute tools → feed results back
- [ ] Tool commands detected using `command_classifier.py` patterns
- [ ] Tools executed via `command_executor.py`
- [ ] Loop terminates when: agent signals done, max_iterations reached, or timeout exceeded
- [ ] Each iteration's tool calls and results are logged in the run record
- [ ] If `stream: true`, each iteration emits SSE events (tool_call, tool_result, iteration_complete)

**Technical Notes:**
- File: create `backend/app/services/agent_runner.py`
- Import `classify_commands()` from `command_classifier.py`
- Import `execute_command()` from `command_executor.py`
- Respect `agent.timeout_seconds` via `asyncio.wait_for()`
- Pattern: similar to `_run_phase()` in `pipelines.py:177-656` but with tool loop

**Complexity:** Large

---

### Story 1.3: Agent Memory Context

**As a** user, **I want** agents with `memory_enabled: true` to remember context from prior runs **so that** they can build on previous work.

**Acceptance Criteria:**
- [ ] When `agent.memory_enabled` is true, prior run outputs are stored in a memory table
- [ ] On new runs, the last N outputs (configurable, default 5) are injected into the system prompt as context
- [ ] Memory is scoped per agent (each agent has its own memory)
- [ ] Memory can be cleared via `DELETE /v1/agents/{agent_id}/memory`
- [ ] Memory entries include: run_id, task, output_summary, created_at

**Technical Notes:**
- Create `agent_memory` table (or reuse `memory_files` with agent scope)
- File: `backend/app/models/agent_memory.py` (new)
- Add Alembic migration
- Inject memory into system prompt in `agent_runner.py` before LLM call

**Complexity:** Medium

---

### Story 1.4: Agent Run History

**As a** user, **I want to** view past agent runs via API **so that** I can review outputs and debug issues.

**Acceptance Criteria:**
- [ ] `GET /v1/agents/{agent_id}/runs` returns paginated list of runs
- [ ] Each run includes: run_id, task, status, output (truncated), tokens, duration, created_at
- [ ] `GET /v1/agents/{agent_id}/runs/{run_id}` returns full run detail including tool call logs
- [ ] Runs are queryable by status filter (`?status=completed`)

**Technical Notes:**
- Create `agent_runs` table: id, agent_id, task, status, output, tool_log (JSONB), input_tokens, output_tokens, duration_ms, created_at
- File: `backend/app/models/agent_run.py` (new)
- Add Alembic migration
- Add routes in `backend/app/routes/agents.py`

**Complexity:** Medium

---

### Story 1.5: Frontend — Run Agent from Detail Page

**As a** user, **I want to** run an agent directly from the agent detail page in the UI **so that** I can test agents without creating pipelines.

**Acceptance Criteria:**
- [ ] Agent detail page (`frontend/src/app/(main)/agents/[id]/page.tsx`) has a "Run" button
- [ ] Clicking "Run" opens a modal with a task input textarea
- [ ] Submitting starts the agent run and shows streaming output
- [ ] Output panel displays: status badge, streaming text, tool calls (collapsible), token count, duration
- [ ] "View History" tab shows past runs for this agent
- [ ] Error states handled gracefully (timeout, model unavailable)

**Technical Notes:**
- File: `frontend/src/app/(main)/agents/[id]/page.tsx`
- Use SSE via `EventSource` for streaming (pattern from workbench/[id]/page.tsx)
- Reuse markdown rendering from chat page

**Complexity:** Medium

---

## Epic 2: Pipeline Parallel Execution

**Goal:** Allow pipeline phases to execute concurrently when they have no dependencies on each other.

**Spec Reference:** DEVFORGEAI_SPEC.md Section 4.2 — "Multiple agents can run simultaneously"

**Current State:** Pipelines execute strictly sequentially (`pipelines.py:658-673`). Each phase waits for the previous phase to complete before starting.

---

### Story 2.1: Phase Dependency Graph

**As a** developer, **I want to** define dependency relationships between phases **so that** independent phases can be identified for parallel execution.

**Acceptance Criteria:**
- [ ] Phase template schema extended with `depends_on: string[]` (list of phase names)
- [ ] Phases with no dependencies (or whose dependencies are all complete) are eligible to run concurrently
- [ ] Existing methods (BMAD, GSD, SuperPowers) default to sequential chains (each phase depends on the previous)
- [ ] Validation: circular dependencies rejected at creation time
- [ ] `GET /v1/workbench/pipelines/methods/{method_id}/phases` response includes `depends_on` field

**Technical Notes:**
- File: `backend/app/services/phase_templates.py` — add `depends_on` key to each phase dict
- Default: `depends_on: [previous_phase_name]` for all existing phases
- Topological sort to determine execution order: use `graphlib.TopologicalSorter` (stdlib)

**Complexity:** Medium

---

### Story 2.2: Parallel Phase Executor

**As a** user, **I want** independent phases to run at the same time **so that** pipelines complete faster.

**Acceptance Criteria:**
- [ ] When a phase completes, all phases whose dependencies are now fully met are started concurrently
- [ ] Concurrent phases each get their own `PhaseRun` record
- [ ] Each parallel phase receives context from its specific dependencies (not all prior phases)
- [ ] Pipeline `current_phase_index` replaced with `active_phases: string[]` tracking
- [ ] If any parallel phase fails, other running phases continue (but downstream dependents are blocked)
- [ ] Pipeline completes when all terminal phases (no dependents) are done

**Technical Notes:**
- File: `backend/app/routes/pipelines.py` — refactor `_advance_to_next()` (line 658)
- Replace sequential index tracking with dependency-aware scheduler
- Use `asyncio.gather()` or task group for concurrent phase execution
- Each phase task is independent `_run_phase()` call

**Complexity:** Large

---

### Story 2.3: Parallel Phase Approval UX

**As a** user, **I want to** approve/reject parallel phases independently **so that** I can review each agent's output separately.

**Acceptance Criteria:**
- [ ] When multiple phases are awaiting approval, the UI shows all of them in a list
- [ ] Each phase has its own Approve / Reject / Skip controls
- [ ] Approving one phase doesn't affect others
- [ ] Rejecting one phase re-runs only that phase
- [ ] Pipeline SSE stream emits events for each parallel phase independently
- [ ] Progress indicator shows "3 of 6 phases complete" (not sequential step number)

**Technical Notes:**
- File: `backend/app/routes/pipelines.py` — modify approve/reject endpoints to accept `phase_name` parameter
- File: `frontend/src/app/(main)/workbench/pipelines/[id]/page.tsx` — render multiple active phases
- SSE events: add `phase_name` field to distinguish parallel events

**Complexity:** Medium

---

### Story 2.4: Parallel Context Merging

**As a** developer, **I want** downstream phases to receive merged context from multiple parent phases **so that** they have complete information.

**Acceptance Criteria:**
- [ ] When a phase depends on multiple completed phases, their artifacts are merged into the input context
- [ ] Merge strategy: concatenate artifacts with clear section headers (e.g., "## Output from [phase_name]")
- [ ] If parent artifacts are JSON, merge into a single JSON object with phase-name keys
- [ ] If parent artifacts are code, concatenate with file-boundary markers
- [ ] Context size validated against model's context window before LLM call

**Technical Notes:**
- File: `backend/app/routes/pipelines.py` — modify context building in `_run_phase()` (lines 330-376)
- Add `_merge_parent_contexts(pipeline, phase_name)` helper function
- Existing pattern: `input_context` field on PhaseRun model already supports this

**Complexity:** Medium

---

### Story 2.5: Pipeline Visualization — Swim Lane View

**As a** user, **I want** the pipeline execution view to show parallel phases as swim lanes **so that** I can see which phases ran concurrently.

**Acceptance Criteria:**
- [ ] Pipeline detail page renders a horizontal timeline with swim lanes
- [ ] Sequential phases appear one after another; parallel phases appear side-by-side
- [ ] Each phase shows: name, agent role, status (color-coded), duration
- [ ] Dependency arrows connect phases to their dependencies
- [ ] Currently-running phases have a pulsing indicator
- [ ] Completed phases show token count and cost

**Technical Notes:**
- File: `frontend/src/app/(main)/workbench/pipelines/[id]/page.tsx`
- Consider using a simple CSS grid layout (no external library needed for basic swim lanes)
- Alternatively, use React Flow for interactive dependency graph visualization
- Phase data already available from `GET /v1/workbench/pipelines/{id}`

**Complexity:** Medium

---

## Epic 3: Conditional Workflow Branching

**Goal:** Allow workflows to make decisions based on phase outputs, routing to different next-steps conditionally.

**Spec Reference:** DEVFORGEAI_SPEC.md Section 4.1 — workflow step `on_failure: "retry_with_feedback"` pattern

**Current State:** Pipelines only support linear flow. No if/else branching. Retry exists but only for failed phases.

---

### Story 3.1: Phase Condition Schema

**As a** developer, **I want to** define conditions on phase transitions **so that** workflows can branch based on agent output.

**Acceptance Criteria:**
- [ ] Phase template schema extended with optional `condition` field
- [ ] Condition format: `{ field: string, operator: "equals"|"contains"|"gt"|"lt"|"exists", value: any }`
- [ ] Conditions evaluated against the parent phase's output artifact (parsed as JSON)
- [ ] If condition is true, this phase executes; if false, it is skipped
- [ ] Multiple conditions joined with AND logic (all must be true)
- [ ] Phases without conditions always execute (backward compatible)

**Technical Notes:**
- File: `backend/app/services/phase_templates.py` — add `condition` to phase dict schema
- File: `backend/app/routes/pipelines.py` — add `_evaluate_condition()` before `_run_phase()`
- JSON path evaluation: use simple dict key access (no need for jsonpath library)

**Complexity:** Medium

---

### Story 3.2: Branch Phase Type

**As a** user, **I want** a "branch" phase type that routes to different downstream phases **so that** workflows can take different paths.

**Acceptance Criteria:**
- [ ] New phase type: `branch` (no agent execution, just routing logic)
- [ ] Branch phase definition includes `branches: [{ condition, target_phase }]` and `default_phase`
- [ ] The branch evaluates its parent's output against each condition in order
- [ ] First matching condition routes to that target phase
- [ ] If no condition matches, routes to `default_phase`
- [ ] Branch phase completes instantly (no LLM call, no tokens)

**Technical Notes:**
- File: `backend/app/routes/pipelines.py` — add branch handling in `_advance_to_next()`
- Branch phases need to be distinguishable: add `phase_type: "agent"|"branch"` to schema
- Target phases referenced by name, resolved to index at runtime

**Complexity:** Medium

---

### Story 3.3: Retry with Feedback Loop

**As a** user, **I want** phases to automatically retry with reviewer feedback **so that** quality improves without manual intervention.

**Acceptance Criteria:**
- [ ] Phase template supports `on_failure: "retry_with_feedback"` and `max_retries: N`
- [ ] When a reviewer phase outputs `verdict: "reject"`, the upstream phase re-runs with the review feedback injected
- [ ] Retry count tracked on the PhaseRun record
- [ ] After `max_retries` exhausted, pipeline pauses for manual approval
- [ ] SSE events include retry count and feedback summary
- [ ] Retry context includes: original task + prior output + reviewer feedback

**Technical Notes:**
- File: `backend/app/routes/pipelines.py` — extend reject handling (line 949)
- Add `retry_count` and `max_retries` to PhaseRun model
- Reviewer phases already output structured JSON with `verdict` field (see phase_templates.py line 132)

**Complexity:** Medium

---

### Story 3.4: Frontend — Branch Visualization

**As a** user, **I want** the pipeline view to show branching paths **so that** I can see which path the workflow took.

**Acceptance Criteria:**
- [ ] Branch phases render as diamond decision nodes in the pipeline view
- [ ] Active path highlighted; inactive branches grayed out
- [ ] Hover on branch node shows the condition that was evaluated and the result
- [ ] Retry loops shown as a circular arrow on the retried phase
- [ ] Branch history visible: which path was taken and why

**Technical Notes:**
- File: `frontend/src/app/(main)/workbench/pipelines/[id]/page.tsx`
- Branch phases included in pipeline.phases array with `phase_type: "branch"`
- Render differently from agent phases (diamond shape vs rectangle)

**Complexity:** Small

---

## Epic 4: Visual Workflow Builder

**Goal:** Provide a drag-and-drop UI for designing custom multi-agent workflows.

**Spec Reference:** DEVFORGEAI_SPEC.md Section 8.3 — "Visual workflow editor"

**Current State:** Pipelines use hardcoded method templates (BMAD, GSD, SuperPowers). No visual editor exists. Workflow creation is API-only.

---

### Story 4.1: Workflow Builder Page Shell

**As a** user, **I want** a dedicated `/workbench/builder` page **so that** I can visually design workflows.

**Acceptance Criteria:**
- [ ] New page at `/(main)/workbench/builder` accessible from workbench home
- [ ] Page layout: left sidebar (agent palette), center canvas (workflow graph), right panel (selected node properties)
- [ ] Top toolbar: Save, Load, Run, Clear, Undo/Redo
- [ ] Empty state: "Drag agents from the left to start building your workflow"
- [ ] Navigation: workbench home links to builder; builder links back to workbench

**Technical Notes:**
- File: create `frontend/src/app/(main)/workbench/builder/page.tsx`
- Use React Flow (`@xyflow/react`) for the canvas — it handles nodes, edges, drag/drop, zoom/pan
- Install: `npm install @xyflow/react`

**Complexity:** Medium

---

### Story 4.2: Agent Node Palette

**As a** user, **I want to** drag agent types from a palette onto the canvas **so that** I can add steps to my workflow.

**Acceptance Criteria:**
- [ ] Left sidebar lists all 7 agent types (Coder, Researcher, Designer, Reviewer, Planner, Executor, Writer)
- [ ] Each agent type shown with icon, name, and brief description
- [ ] Drag an agent type onto the canvas to create a new node
- [ ] Node displays: agent name, type badge, model (configurable), status indicator
- [ ] Custom agents (from `/v1/agents`) also appear in the palette
- [ ] Palette is searchable/filterable

**Technical Notes:**
- Fetch agent types from `GET /v1/agents/defaults` + `GET /v1/agents`
- React Flow: implement `onDrop` handler to create new node at drop position
- Node data: `{ agentType, agentId?, model, systemPrompt, tools, config }`

**Complexity:** Medium

---

### Story 4.3: Edge Connections & Dependencies

**As a** user, **I want to** connect nodes with edges **so that** I can define the execution order and data flow.

**Acceptance Criteria:**
- [ ] Drag from a node's output handle to another node's input handle to create an edge
- [ ] Edges represent data flow (parent output → child input context)
- [ ] Multiple inputs allowed (parallel merge)
- [ ] Multiple outputs allowed (fan-out / parallel execution)
- [ ] Circular dependencies rejected with visual warning
- [ ] Edge labels show what data flows through (optional)
- [ ] Edges can be deleted by selecting and pressing Delete

**Technical Notes:**
- React Flow handles edge creation natively
- Validate DAG on every edge addition using topological sort
- Edge data maps to `depends_on` field in phase schema

**Complexity:** Small

---

### Story 4.4: Node Configuration Panel

**As a** user, **I want to** configure each node's properties **so that** I can customize agent behavior per step.

**Acceptance Criteria:**
- [ ] Clicking a node opens the right panel with its configuration
- [ ] Configurable fields: name, agent type, model (dropdown), system prompt (textarea), tools (checkboxes), max_iterations, timeout
- [ ] Model dropdown fetches from `GET /v1/models`
- [ ] Changes save immediately to node data (no separate save button)
- [ ] Artifact type selector: JSON, Code, Markdown
- [ ] Optional condition field for conditional execution (links to Epic 3)

**Technical Notes:**
- File: component within `workbench/builder/page.tsx` or extracted to `components/WorkflowNodeConfig.tsx`
- React Flow: use `onNodeClick` to select node, render config panel from `node.data`

**Complexity:** Medium

---

### Story 4.5: Save & Load Workflows

**As a** user, **I want to** save my workflow design and load it later **so that** I can reuse and iterate on workflows.

**Acceptance Criteria:**
- [ ] "Save" button serializes the graph (nodes + edges + positions) and saves via API
- [ ] `POST /v1/workflows/custom` creates a new custom workflow
- [ ] `PUT /v1/workflows/custom/{id}` updates an existing workflow
- [ ] `GET /v1/workflows/custom` lists all saved custom workflows
- [ ] "Load" button opens a dialog listing saved workflows for selection
- [ ] Loaded workflow restores all nodes, edges, positions, and configurations
- [ ] Workflow metadata: name, description, created_at, updated_at

**Technical Notes:**
- Backend: create `custom_workflows` table (id, user_id, name, description, graph_data JSONB, created_at, updated_at)
- File: create `backend/app/routes/custom_workflows.py`
- Graph serialized as React Flow's `{ nodes, edges }` JSON
- Add Alembic migration

**Complexity:** Medium

---

### Story 4.6: Run Workflow from Builder

**As a** user, **I want to** run my visual workflow directly from the builder **so that** I can test it immediately.

**Acceptance Criteria:**
- [ ] "Run" button prompts for initial task description
- [ ] Converts the visual graph into a pipeline definition (phases + dependencies)
- [ ] Creates a pipeline via `POST /v1/workbench/pipelines` with the custom method
- [ ] Redirects to the pipeline execution view (`/workbench/pipelines/{id}`)
- [ ] Validation before run: at least one node, no disconnected nodes, valid DAG
- [ ] Error messages for invalid workflow configurations

**Technical Notes:**
- Convert React Flow graph to phase array: topological sort nodes, map node.data to phase template format
- Set `depends_on` from edge connections
- Custom method_id: use `"custom_{workflow_id}"` convention

**Complexity:** Medium

---

## Epic 5: Custom Workflow Templates

**Goal:** Let users create, share, and manage reusable workflow method templates beyond the built-in BMAD/GSD/SuperPowers.

**Spec Reference:** DEVFORGEAI_SPEC.md Section 4.1 — workflow definitions with trigger keywords

**Current State:** Methods are hardcoded in `phase_templates.py`. Users cannot create new methods.

---

### Story 5.1: Custom Method CRUD API

**As a** user, **I want to** create custom method templates via API **so that** I can define reusable multi-agent workflows.

**Acceptance Criteria:**
- [ ] `POST /v1/methods/custom` creates a new method with name, description, phases array
- [ ] `GET /v1/methods/custom` lists user-created methods
- [ ] `PUT /v1/methods/custom/{id}` updates a method
- [ ] `DELETE /v1/methods/custom/{id}` deletes a method
- [ ] Custom methods appear alongside built-in methods in `GET /v1/methods/`
- [ ] Phase format matches existing schema (name, role, default_model, system_prompt, artifact_type, depends_on)
- [ ] Trigger keywords for auto-detection (optional)

**Technical Notes:**
- Create `custom_methods` table: id, user_id, name, description, phases (JSONB), trigger_keywords (JSONB), is_active, created_at, updated_at
- File: extend `backend/app/routes/methods.py` or create new route file
- `phase_templates.py` — add `get_method_phases()` that checks custom methods before built-in
- Add Alembic migration

**Complexity:** Medium

---

### Story 5.2: Method Template Import/Export

**As a** user, **I want to** export and import method templates as JSON **so that** I can share them and back them up.

**Acceptance Criteria:**
- [ ] `GET /v1/methods/custom/{id}/export` returns the complete method as downloadable JSON
- [ ] `POST /v1/methods/custom/import` accepts a JSON file and creates a new method
- [ ] Exported JSON includes: name, description, phases, trigger_keywords, version
- [ ] Import validates schema before creating
- [ ] Duplicate detection: warn if method with same name exists

**Technical Notes:**
- Export format: `{ version: "1.0", method: { ...method_data } }`
- Import endpoint: parse JSON, validate phase schema, create via same logic as CRUD

**Complexity:** Small

---

### Story 5.3: Method from Pipeline History

**As a** user, **I want to** save a completed pipeline run as a new method template **so that** I can reuse successful workflows.

**Acceptance Criteria:**
- [ ] Pipeline detail page has "Save as Template" button (visible when pipeline is completed)
- [ ] Clicking opens dialog to name and describe the template
- [ ] Saves the pipeline's phase configuration as a new custom method
- [ ] Model overrides from the run preserved as defaults in the template
- [ ] System prompts from the run can be optionally saved (may contain task-specific context)

**Technical Notes:**
- File: `frontend/src/app/(main)/workbench/pipelines/[id]/page.tsx` — add button
- Backend: pipeline phases already stored in `pipeline.phases` JSONB column
- Convert pipeline.phases to method template format

**Complexity:** Small

---

### Story 5.4: Frontend — Method Manager

**As a** user, **I want** a UI to browse, create, and manage custom methods **so that** I don't need to use the API directly.

**Acceptance Criteria:**
- [ ] `/methods` page shows built-in methods (read-only) and custom methods (editable)
- [ ] Custom methods have Edit and Delete buttons
- [ ] "Create Method" button opens the workflow builder (Epic 4) in template mode
- [ ] Method detail view shows phase list, dependencies, and model defaults
- [ ] Import/Export buttons for JSON file operations
- [ ] Search/filter by name and keyword

**Technical Notes:**
- File: `frontend/src/app/(main)/methods/page.tsx` (extend existing)
- Methods page currently exists but only shows built-in methods
- Add CRUD operations for custom methods

**Complexity:** Medium

---

## Epic 6: Enhanced Analytics Dashboard

**Goal:** Provide comprehensive analytics covering cost trends, model performance, agent efficiency, and usage forecasting.

**Spec Reference:** CHARTER.md Section 7 — "Cost analytics", "Usage analytics"

**Current State:** Basic stats page exists (`frontend/stats/page.tsx`) showing 7-day cost/usage by model. Backend has `GET /v1/stats/costs` and `GET /v1/stats/usage`.

---

### Story 6.1: Cost Trend Charts

**As a** user, **I want to** see cost trends over time as charts **so that** I can understand spending patterns.

**Acceptance Criteria:**
- [ ] `GET /v1/stats/costs/daily?days=30` returns daily cost breakdown
- [ ] Stats page displays a line chart of daily cost over selectable time range (7, 14, 30 days)
- [ ] Chart shows total cost line and per-model stacked area
- [ ] Hover tooltip shows exact cost per model for that day
- [ ] Summary cards show: total period cost, daily average, cost change vs prior period (%)

**Technical Notes:**
- Backend: `backend/app/routes/stats.py` — add daily aggregation query (GROUP BY date)
- Frontend: use Recharts or Chart.js for visualization
- Install: `npm install recharts` (React-friendly, lightweight)

**Complexity:** Medium

---

### Story 6.2: Model Performance Comparison

**As a** user, **I want to** compare model performance metrics **so that** I can make informed routing decisions.

**Acceptance Criteria:**
- [ ] `GET /v1/stats/models/performance?days=7` returns per-model metrics
- [ ] Metrics: avg_latency_ms, p95_latency_ms, success_rate, avg_tokens_per_request, total_requests
- [ ] Stats page shows comparison table sortable by any metric
- [ ] Bar chart comparing latency across models
- [ ] Highlight: cheapest model, fastest model, most reliable model

**Technical Notes:**
- Backend: query `request_logs` grouped by model_id with aggregation functions
- P95: use PostgreSQL `percentile_cont(0.95)` function
- File: `backend/app/routes/stats.py` — add new endpoint

**Complexity:** Medium

---

### Story 6.3: Agent Efficiency Metrics

**As a** user, **I want to** see how each agent performs across pipeline runs **so that** I can optimize agent configurations.

**Acceptance Criteria:**
- [ ] `GET /v1/stats/agents?days=7` returns per-agent metrics
- [ ] Metrics: total_runs, success_rate, avg_tokens, avg_duration, retry_rate
- [ ] Stats page shows agent performance table
- [ ] Click agent row to see run history detail
- [ ] Compare agents of same type (e.g., two different Coder agents)

**Technical Notes:**
- Backend: query `workbench_phase_runs` grouped by agent_role
- Join with `agents` table for agent names
- File: `backend/app/routes/stats.py`

**Complexity:** Medium

---

### Story 6.4: Token Usage Forecasting

**As a** user, **I want to** see projected token usage for the current billing period **so that** I can manage my budget.

**Acceptance Criteria:**
- [ ] Stats page shows projected monthly cost based on current usage rate
- [ ] Projection calculated from daily average × remaining days in month
- [ ] Visual: progress bar showing actual vs projected vs budget limit
- [ ] If projection exceeds a user-set budget threshold, show warning
- [ ] Budget threshold configurable in Settings page

**Technical Notes:**
- Frontend calculation: `(total_cost / days_elapsed) * days_in_month`
- Budget threshold stored in user preferences (`GET /v1/user` preferences JSON)
- No new backend endpoint needed — derive from existing cost data

**Complexity:** Small

---

### Story 6.5: Export Analytics Reports

**As a** user, **I want to** export analytics data as CSV **so that** I can use it in external tools.

**Acceptance Criteria:**
- [ ] Each stats section has an "Export CSV" button
- [ ] CSV includes all displayed columns plus timestamps
- [ ] Filename format: `devforgeai_costs_2026-04-01_2026-04-08.csv`
- [ ] Export endpoint: `GET /v1/stats/export?type=costs&days=30&format=csv`
- [ ] Response Content-Type: `text/csv` with Content-Disposition attachment header

**Technical Notes:**
- Backend: `backend/app/routes/stats.py` — add export endpoint
- Use Python `csv` module with `io.StringIO` for in-memory CSV generation
- Frontend: trigger download via `<a href="..." download>` pattern

**Complexity:** Small

---

## Epic 7: OAuth & Advanced Auth

**Goal:** Add OAuth provider support (GitHub), session management, and role-based access control refinements.

**Spec Reference:** CHARTER.md Section 8 — "Multi-user Support: Auth, roles, per-user settings"

**Current State:** JWT auth exists (`backend/app/middleware/auth.py`). Login endpoint works (`POST /v1/auth/login`). Users stored in `collab_users.json`. GitHub columns exist but aren't wired. OpenRouter OAuth callback exists in frontend.

---

### Story 7.1: GitHub OAuth Flow

**As a** user, **I want to** log in with my GitHub account **so that** I don't need to manage a separate password.

**Acceptance Criteria:**
- [ ] `GET /v1/auth/github` redirects to GitHub OAuth authorization URL
- [ ] `GET /v1/auth/github/callback` handles the OAuth callback with authorization code
- [ ] On callback: exchange code for access token, fetch GitHub profile, create or update user
- [ ] User record stores: github_id, github_login, avatar_url, github_token (encrypted)
- [ ] Returns JWT token same as password login
- [ ] Frontend: "Sign in with GitHub" button on login page
- [ ] If user exists with same email, link accounts

**Technical Notes:**
- File: create `backend/app/routes/oauth.py`
- GitHub OAuth app: client_id and client_secret in `.env`
- Use `httpx` for GitHub API calls (already in requirements)
- collab_users.json already has github_id, github_login, avatar_url, github_token fields
- Frontend: `frontend/src/app/auth/` — extend existing auth pages

**Complexity:** Medium

---

### Story 7.2: OAuth Provider Framework

**As a** developer, **I want** a generic OAuth provider framework **so that** adding new OAuth providers (Google, Microsoft) is straightforward.

**Acceptance Criteria:**
- [ ] `BaseOAuthProvider` abstract class with methods: `get_auth_url()`, `exchange_code()`, `get_user_profile()`
- [ ] `GitHubOAuthProvider` implements the base class
- [ ] Provider configuration via `.env` variables: `{PROVIDER}_CLIENT_ID`, `{PROVIDER}_CLIENT_SECRET`
- [ ] Provider registry: `OAUTH_PROVIDERS = { "github": GitHubOAuthProvider, ... }`
- [ ] Routes auto-generated from registry: `/v1/auth/{provider}` and `/v1/auth/{provider}/callback`
- [ ] `GET /v1/auth/providers` returns list of configured OAuth providers

**Technical Notes:**
- File: create `backend/app/services/oauth.py`
- Pattern: strategy pattern with provider registry
- Each provider needs: auth_url, token_url, user_info_url, scopes

**Complexity:** Medium

---

### Story 7.3: Session Management

**As a** user, **I want** my sessions tracked and manageable **so that** I can log out from specific devices and see login history.

**Acceptance Criteria:**
- [ ] `GET /v1/auth/sessions` returns list of active sessions for current user
- [ ] Each session shows: device info (user-agent), IP address, created_at, last_active
- [ ] `DELETE /v1/auth/sessions/{session_id}` revokes a specific session
- [ ] `DELETE /v1/auth/sessions` revokes all sessions except current (force logout everywhere)
- [ ] Sessions stored in Redis with TTL matching JWT expiry
- [ ] Login event creates session record

**Technical Notes:**
- Redis key pattern: `session:{user_id}:{session_id}` with JWT payload as value
- Session ID: UUID generated at login, included in JWT claims
- Auth middleware: verify session exists in Redis (not just JWT validity)
- File: extend `backend/app/routes/collaboration.py` auth section

**Complexity:** Medium

---

### Story 7.4: Role-Based Access Control

**As an** admin, **I want** granular permission control **so that** different users can access different features.

**Acceptance Criteria:**
- [ ] Roles: `owner`, `admin`, `member`, `viewer` (already in user schema)
- [ ] Permission matrix defined:
  - `viewer`: read-only (GET endpoints only)
  - `member`: viewer + create/run agents and pipelines
  - `admin`: member + manage models, personas, users
  - `owner`: admin + system config, OAuth setup, dangerous operations
- [ ] Middleware decorator: `@require_role("admin")` applied to protected endpoints
- [ ] Insufficient permission returns 403 with clear error message
- [ ] Role check uses `request.state.user["role"]`

**Technical Notes:**
- File: create `backend/app/middleware/rbac.py`
- Decorator pattern: `def require_role(*roles)` returns FastAPI dependency
- Apply to routes that need protection (model CRUD, user management, system config)
- Master API key gets `owner` role automatically

**Complexity:** Medium

---

### Story 7.5: Frontend — Login & Auth Pages

**As a** user, **I want** a proper login page with OAuth buttons **so that** I can authenticate through the web UI.

**Acceptance Criteria:**
- [ ] Login page at `/auth/login` with username/password form and OAuth buttons
- [ ] JWT token stored in `httpOnly` cookie or `localStorage` (with CSRF protection)
- [ ] Auth state managed globally (React Context or cookie check)
- [ ] Protected routes redirect to login if not authenticated
- [ ] User avatar and name shown in header/sidebar when logged in
- [ ] Logout button clears token and redirects to login
- [ ] Registration page at `/auth/register` (if self-registration enabled)

**Technical Notes:**
- Frontend auth pages partially exist at `frontend/src/app/auth/`
- OpenRouter callback page exists: `frontend/src/app/auth/openrouter/callback/page.tsx`
- Extend with login page and auth context provider
- API client: add Authorization header interceptor

**Complexity:** Medium

---

## Epic 8: Real-time Collaboration

**Goal:** Enable multiple users to collaborate in real-time on conversations, workspaces, and agent runs.

**Spec Reference:** CHARTER.md Section 8 — "Collaboration (shared workspaces, @mentions)"

**Current State:** Session handoff exists (`POST /v1/collab/handoff`). Shared workspaces have basic CRUD (`/v1/collab/workspaces`). No real-time sync.

---

### Story 8.1: WebSocket Infrastructure

**As a** developer, **I want** WebSocket support in the backend **so that** real-time features can be built on it.

**Acceptance Criteria:**
- [ ] WebSocket endpoint at `/ws` accepts authenticated connections
- [ ] JWT token sent as query param or first message for auth
- [ ] Connected clients tracked in Redis: `ws:{user_id}` → connection metadata
- [ ] Heartbeat ping/pong every 30 seconds; disconnect after 3 missed pings
- [ ] Message format: `{ type: string, payload: object, timestamp: string }`
- [ ] Channel subscription: clients subscribe to topics (conversation, workspace, pipeline)
- [ ] Graceful disconnect cleanup (remove from Redis, notify subscribers)

**Technical Notes:**
- FastAPI native WebSocket support: `@app.websocket("/ws")`
- File: create `backend/app/routes/websocket.py`
- Use Redis pub/sub for cross-process message broadcasting
- Connection manager: track active connections per user in memory + Redis

**Complexity:** Large

---

### Story 8.2: Presence & Activity Indicators

**As a** user, **I want to** see who is online and what they're working on **so that** I can collaborate effectively.

**Acceptance Criteria:**
- [ ] Online users list visible in sidebar (green dot = online, gray = offline)
- [ ] Each user shows current activity: "Viewing /chat", "Running pipeline #5", "Editing agent"
- [ ] Activity updated on page navigation via WebSocket message
- [ ] `GET /v1/collab/presence` returns current online users and activities (REST fallback)
- [ ] Presence TTL: user shows offline after 2 minutes of no heartbeat

**Technical Notes:**
- Redis key: `presence:{user_id}` → `{ page, activity, last_seen }` with 120s TTL
- WebSocket: send presence update on route change
- Frontend: sidebar component with user list, poll or subscribe via WebSocket
- File: extend `backend/app/routes/collaboration.py`

**Complexity:** Medium

---

### Story 8.3: Shared Conversation Viewing

**As a** user, **I want to** share a conversation with a teammate **so that** they can see and continue it.

**Acceptance Criteria:**
- [ ] Conversation owner can share via "Share" button → generates a share token
- [ ] Share link format: `/chat?share={token}`
- [ ] Shared conversation is read-only by default; owner can grant write access
- [ ] Shared users see new messages in real-time via WebSocket
- [ ] `POST /v1/conversations/{id}/share` creates share token with permissions
- [ ] `GET /v1/conversations/shared` lists conversations shared with current user
- [ ] Share can be revoked by owner

**Technical Notes:**
- Share token: signed JWT containing conversation_id, permissions, expiry
- Or: `conversation_shares` table (conversation_id, user_id, permission, token, created_at)
- WebSocket: broadcast new messages to all subscribers of a conversation channel
- File: extend `backend/app/routes/conversations.py`

**Complexity:** Medium

---

### Story 8.4: @Mentions in Chat

**As a** user, **I want to** @mention teammates in chat **so that** they get notified and can jump into the conversation.

**Acceptance Criteria:**
- [ ] Typing `@` in chat input shows autocomplete dropdown of team members
- [ ] Selecting a user inserts `@username` into the message
- [ ] When message is sent, mentioned users receive a notification
- [ ] Notification includes: who mentioned them, in which conversation, message preview
- [ ] Clicking notification opens the conversation at the mentioned message
- [ ] `GET /v1/notifications` returns unread notifications for current user
- [ ] `POST /v1/notifications/{id}/read` marks as read

**Technical Notes:**
- Parse mentions: regex `/@(\w+)/g` on message content
- Notification storage: Redis list or `notifications` table
- WebSocket: push notification to mentioned user if online
- Frontend: autocomplete component in chat input
- File: create `backend/app/routes/notifications.py`

**Complexity:** Medium

---

### Story 8.5: Collaborative Pipeline Approval

**As a** user, **I want** multiple team members to approve pipeline phases **so that** we can review work together.

**Acceptance Criteria:**
- [ ] Pipeline creation supports `approvers: string[]` (list of user IDs)
- [ ] When a phase needs approval, all listed approvers are notified
- [ ] Approval requires majority (configurable: any one, majority, all)
- [ ] Each approver can approve or reject independently
- [ ] Approval status shows who has approved and who is pending
- [ ] WebSocket: real-time update when any approver acts
- [ ] If no approvers specified, falls back to pipeline creator

**Technical Notes:**
- Extend `workbench_pipelines` table with `approvers` JSONB column
- Extend `workbench_phase_runs` with `approvals` JSONB (list of {user_id, action, timestamp})
- File: extend `backend/app/routes/pipelines.py` approve endpoint
- Notification integration from Story 8.4

**Complexity:** Medium

---

## Epic 9: Voice Interface

**Goal:** Add speech-to-text input and text-to-speech output for hands-free AI interaction.

**Spec Reference:** project-context.md Section 3 — "Voice input/output" in Phase 3.0 backlog

**Current State:** No voice functionality exists. No audio libraries installed. Greenfield.

---

### Story 9.1: Speech-to-Text Input

**As a** user, **I want to** speak into my microphone and have it transcribed as chat input **so that** I can interact hands-free.

**Acceptance Criteria:**
- [ ] Microphone button in chat input area
- [ ] Click to start recording; click again to stop (or auto-stop on silence after 3 seconds)
- [ ] Audio sent to transcription API (Whisper via OpenAI, or Google Speech-to-Text)
- [ ] Transcribed text appears in chat input field for review before sending
- [ ] Visual indicator: recording state (pulsing red dot), processing state (spinner)
- [ ] `POST /v1/audio/transcribe` accepts audio blob and returns transcribed text
- [ ] Supported formats: webm, mp3, wav

**Technical Notes:**
- Frontend: use `MediaRecorder` Web API for audio capture
- Backend: create `backend/app/routes/audio.py`
- Transcription: use OpenAI Whisper API (`openai.audio.transcriptions.create`) or Google Speech-to-Text
- Audio upload: multipart form data
- Install backend: `openai` package (already present for model routing)

**Complexity:** Medium

---

### Story 9.2: Text-to-Speech Output

**As a** user, **I want** the AI response to be read aloud **so that** I can listen instead of reading.

**Acceptance Criteria:**
- [ ] Each assistant message has a "Listen" (speaker icon) button
- [ ] Clicking sends the message text to TTS API and plays audio
- [ ] Audio streams as it generates (not wait for full synthesis)
- [ ] Playback controls: pause, resume, stop
- [ ] Voice selection: at least 2-3 voice options (configurable in Settings)
- [ ] `POST /v1/audio/synthesize` accepts text and returns audio stream
- [ ] Keyboard shortcut: `Ctrl+Shift+L` to read last assistant message

**Technical Notes:**
- Frontend: use `HTMLAudioElement` or Web Audio API for playback
- Backend: use OpenAI TTS API (`openai.audio.speech.create`) or Google TTS
- Streaming: return audio as chunked response (audio/mpeg or audio/wav)
- File: extend `backend/app/routes/audio.py`

**Complexity:** Medium

---

### Story 9.3: Continuous Voice Mode

**As a** user, **I want** a continuous conversation mode where I speak and the AI responds with voice **so that** I can have a natural dialogue.

**Acceptance Criteria:**
- [ ] "Voice Mode" toggle in chat header
- [ ] When enabled: auto-listen → transcribe → send → generate response → speak response → auto-listen again
- [ ] Visual: conversation transcript appears in chat as normal messages
- [ ] "Stop" button to exit voice mode
- [ ] Push-to-talk alternative (hold spacebar to record)
- [ ] Configurable auto-stop silence duration (1-5 seconds)
- [ ] Wake word detection optional (future: "Hey Agent")

**Technical Notes:**
- Frontend state machine: idle → listening → transcribing → waiting → speaking → idle
- Chain: Story 9.1 transcribe → normal chat flow → Story 9.2 synthesize
- File: create `frontend/src/components/VoiceMode.tsx`
- Use `AudioContext` for overlap detection (don't record while speaking)

**Complexity:** Large

---

### Story 9.4: Voice-Triggered Workflows

**As a** user, **I want to** trigger workflows by voice command **so that** I can start complex tasks hands-free.

**Acceptance Criteria:**
- [ ] Voice input parsed for workflow trigger keywords (from method `trigger_keywords`)
- [ ] If trigger detected, confirm with user: "I'll start the [workflow] pipeline. Proceed?"
- [ ] User confirms by voice ("yes") or button
- [ ] Pipeline created and executed as normal
- [ ] Voice status updates: "Phase 2 of 5 complete. Researcher found 3 sources."

**Technical Notes:**
- Keyword detection: match transcribed text against `trigger_keywords` from all methods
- Confirmation flow: send a system message asking for confirmation
- Status updates: TTS synthesis of pipeline SSE events
- Depends on: Stories 9.1, 9.2, and pipeline execution

**Complexity:** Medium

---

### Story 9.5: Audio Settings & Provider Config

**As a** user, **I want to** configure voice settings **so that** I can choose my preferred voice and transcription provider.

**Acceptance Criteria:**
- [ ] Settings page section for Voice/Audio
- [ ] Options: transcription provider (OpenAI Whisper, Google), TTS provider (OpenAI, Google, ElevenLabs)
- [ ] Voice selection dropdown (provider-specific voice list)
- [ ] Playback speed: 0.5x, 1x, 1.25x, 1.5x, 2x
- [ ] Auto-silence detection threshold (sensitivity slider)
- [ ] Test buttons: "Test Microphone", "Test Speaker"
- [ ] Provider API keys configurable per provider

**Technical Notes:**
- File: extend `frontend/src/app/(main)/settings/page.tsx`
- Backend: audio settings stored in user preferences JSON
- Voice list: fetch from provider APIs at runtime

**Complexity:** Small

---

## Epic 10: Production Deployment

**Goal:** Production-ready deployment infrastructure with Kubernetes, CI/CD, monitoring, and scaling.

**Spec Reference:** project-context.md Phase 3.0 — "Kubernetes deployment"

**Current State:** Docker Compose works for local dev. Dockerfiles exist for both backend and frontend. No K8s manifests, CI/CD, or monitoring.

---

### Story 10.1: Kubernetes Manifests

**As a** DevOps engineer, **I want** Kubernetes deployment manifests **so that** the app can run in a K8s cluster.

**Acceptance Criteria:**
- [ ] `k8s/` directory with manifests for: backend, frontend, postgres, redis
- [ ] Each service has: Deployment, Service, ConfigMap, Secret
- [ ] Backend: 2 replicas, resource limits (256Mi memory, 500m CPU), liveness/readiness probes
- [ ] Frontend: 2 replicas, resource limits (128Mi memory, 250m CPU)
- [ ] PostgreSQL: StatefulSet with PersistentVolumeClaim (10Gi)
- [ ] Redis: Deployment with PersistentVolumeClaim (1Gi)
- [ ] Ingress resource with TLS termination (nginx-ingress or traefik)
- [ ] Namespace: `devforgeai`
- [ ] Kustomize overlays: `base/`, `dev/`, `prod/`

**Technical Notes:**
- Health check probes: backend has `GET /v1/system/health`, frontend has Next.js built-in
- Secrets: API keys stored as K8s Secrets, mounted as env vars
- Backend port: 18800, Frontend port: 3000
- Inter-service communication: K8s DNS (backend.devforgeai.svc.cluster.local)

**Complexity:** Medium

---

### Story 10.2: Helm Chart

**As a** DevOps engineer, **I want** a Helm chart **so that** deployment configuration is parameterized and reusable.

**Acceptance Criteria:**
- [ ] `helm/devforgeai/` chart with Chart.yaml, values.yaml, templates/
- [ ] Configurable values: replicas, image tags, resource limits, ingress host, TLS, API keys
- [ ] Dependency charts: PostgreSQL (bitnami/postgresql), Redis (bitnami/redis)
- [ ] `helm install devforgeai ./helm/devforgeai -f values-prod.yaml` works
- [ ] `helm upgrade` supports rolling updates with zero downtime
- [ ] Values files: `values.yaml` (defaults), `values-dev.yaml`, `values-prod.yaml`

**Technical Notes:**
- Template all manifest values using Helm `{{ .Values.x }}` syntax
- Use Helm hooks for database migrations (pre-upgrade job running Alembic)
- Chart version follows SemVer

**Complexity:** Medium

---

### Story 10.3: CI/CD Pipeline

**As a** developer, **I want** automated CI/CD **so that** code changes are tested and deployed automatically.

**Acceptance Criteria:**
- [ ] GitHub Actions workflow: `.github/workflows/ci.yml`
- [ ] On push to any branch: lint, type-check, unit tests
- [ ] On push to `main`: build Docker images, push to container registry, deploy to staging
- [ ] On tag `v*`: deploy to production
- [ ] Pipeline stages: lint → test → build → push → deploy
- [ ] Test stage runs: `pytest` (backend), `npm test` (frontend), `npm run build` (frontend)
- [ ] Build stage creates multi-arch Docker images (amd64, arm64)
- [ ] Deploy stage uses `kubectl apply` or `helm upgrade`
- [ ] Notifications: Slack/Discord on failure

**Technical Notes:**
- Container registry: GitHub Container Registry (ghcr.io) or Docker Hub
- Secrets: GitHub Actions secrets for API keys, K8s kubeconfig
- Caching: Docker layer cache, npm cache, pip cache
- File: create `.github/workflows/ci.yml`

**Complexity:** Medium

---

### Story 10.4: Monitoring & Alerting

**As an** operator, **I want** monitoring and alerting **so that** I know when the system is unhealthy.

**Acceptance Criteria:**
- [ ] Prometheus metrics endpoint: `GET /metrics` on backend
- [ ] Metrics exported: request_count, request_latency, token_usage, model_errors, active_pipelines
- [ ] Grafana dashboard with panels: request rate, latency p50/p95/p99, error rate, cost per hour
- [ ] Alerts: error rate > 5%, latency p95 > 10s, disk usage > 80%
- [ ] Log aggregation: structured JSON logging to stdout (K8s captures via fluentd/loki)
- [ ] Health dashboard: PostgreSQL, Redis, LLM providers status

**Technical Notes:**
- Install: `prometheus-client` Python package
- File: create `backend/app/routes/metrics.py` or use middleware
- Grafana: JSON dashboard definition in `k8s/monitoring/grafana-dashboard.json`
- Alert rules: Prometheus AlertManager YAML
- Existing health check: `GET /v1/system/health` can feed into monitoring

**Complexity:** Medium

---

### Story 10.5: Database Migration Strategy

**As a** developer, **I want** a reliable database migration strategy for production **so that** schema changes don't cause downtime.

**Acceptance Criteria:**
- [ ] Alembic migrations run as a pre-deployment step (K8s Job or Helm pre-upgrade hook)
- [ ] Migrations are backward-compatible (add columns as nullable, then backfill, then constrain)
- [ ] Rollback procedure documented: `alembic downgrade -1`
- [ ] Migration testing: CI runs migrations against a fresh database and a copy of prod schema
- [ ] Seed data script for initial deployment (providers, default personas, built-in agents)
- [ ] Database backup before migration (pg_dump to S3 or PVC)

**Technical Notes:**
- File: `k8s/jobs/migrate.yaml` — K8s Job running `alembic upgrade head`
- Helm hook: `pre-upgrade` annotation
- Backup: CronJob running `pg_dump` nightly
- Existing Alembic setup: `backend/alembic/` directory

**Complexity:** Medium

---

## Epic 11: Chat Self-Modification

**Goal:** Allow users to manage system configuration (models, personas, agents) through natural language chat commands.

**Spec Reference:** CHARTER.md Section 8 — "Chat Self-Modification: Add/update models/personas via chat commands"

**Current State:** No chat command parsing exists. All configuration is via dedicated UI pages or API calls.

---

### Story 11.1: Chat Command Parser

**As a** developer, **I want** a command parser that detects system commands in chat messages **so that** natural language configuration is possible.

**Acceptance Criteria:**
- [ ] Parser detects commands in user messages matching patterns like:
  - "add model [name] from [provider]"
  - "create a persona called [name] that [description]"
  - "switch to [model/persona]"
  - "show my models" / "list personas"
  - "delete model [name]"
- [ ] Parser returns structured command: `{ action, entity_type, params }`
- [ ] Ambiguous commands trigger clarification: "Did you mean...?"
- [ ] Commands can be prefixed with `/` for explicit mode: `/add-model gpt-4`
- [ ] Non-command messages pass through to normal chat flow

**Technical Notes:**
- File: create `backend/app/services/chat_command_parser.py`
- Approach: regex patterns for explicit commands + LLM classification for natural language
- Use classifier persona (Llama 3.1 8B) for natural language intent detection
- Return `None` for non-command messages

**Complexity:** Medium

---

### Story 11.2: Model Management via Chat

**As a** user, **I want to** add, remove, and configure models through chat **so that** I don't need to leave the conversation.

**Acceptance Criteria:**
- [ ] "Add model gemini-2.5-pro from google" → creates model via existing API
- [ ] "Remove model [name]" → deletes model (with confirmation)
- [ ] "List my models" → displays model table in chat
- [ ] "Set model [name] as default for coding" → updates persona routing
- [ ] All modifications logged to `system_modifications` table
- [ ] Response includes confirmation with model details

**Technical Notes:**
- File: create `backend/app/services/chat_commands/model_commands.py`
- Reuse existing model CRUD routes internally (call service layer, not HTTP)
- Confirmation for destructive operations: "Are you sure you want to delete [model]? Reply 'yes' to confirm."

**Complexity:** Medium

---

### Story 11.3: Persona Management via Chat

**As a** user, **I want to** create and configure personas through chat **so that** I can set up new AI behaviors conversationally.

**Acceptance Criteria:**
- [ ] "Create a persona called 'SQL Expert' that helps with database queries using Claude" → creates persona
- [ ] Parser extracts: name, description/system_prompt, model preference
- [ ] "Update persona [name] to use [model]" → updates persona
- [ ] "Switch to persona [name]" → changes active persona for current conversation
- [ ] "Show persona [name]" → displays persona config
- [ ] Created persona uses reasonable defaults for unspecified fields

**Technical Notes:**
- Reuse existing persona CRUD service layer
- Default system prompt generated from description using LLM
- Model resolution: match model name fuzzy against `models` table
- File: create `backend/app/services/chat_commands/persona_commands.py`

**Complexity:** Medium

---

### Story 11.4: Workflow Trigger via Chat

**As a** user, **I want to** start workflows from chat by describing what I need **so that** complex tasks begin naturally.

**Acceptance Criteria:**
- [ ] "Build me a landing page for my SaaS product" → detects workflow trigger keywords → starts pipeline
- [ ] Trigger matching uses method `trigger_keywords` from all methods (built-in + custom)
- [ ] If trigger detected, respond: "I can run the [method] pipeline for this. Shall I proceed?"
- [ ] On confirmation, create pipeline and switch to pipeline view (or show status in chat)
- [ ] If no trigger matches but task is complex, suggest: "This seems complex. Want me to run it as a pipeline?"
- [ ] Pipeline status updates posted back to chat

**Technical Notes:**
- Keyword matching: compare user message against all `trigger_keywords` arrays
- Fuzzy match: use simple word overlap or LLM classification
- Pipeline creation: call `POST /v1/workbench/pipelines` internally
- File: extend chat command parser to check triggers before command parsing

**Complexity:** Medium

---

## Epic 12: Advanced Learning & Personalization

**Goal:** Make the system smarter over time by learning from user feedback, usage patterns, and interaction history.

**Spec Reference:** CHARTER.md Section 8 — "Advanced Learning: Preference reinforcement from user feedback"

**Current State:** Basic preference tracking exists (`preference_tracking` table). Memory files (USER.md, CONTEXT.md) exist. No automated learning or feedback loops.

---

### Story 12.1: Explicit Feedback Collection

**As a** user, **I want to** rate AI responses **so that** the system learns which models and approaches I prefer.

**Acceptance Criteria:**
- [ ] Each assistant message has thumbs up / thumbs down buttons
- [ ] Optional: text feedback field on thumbs down ("What went wrong?")
- [ ] Feedback stored: `{ message_id, conversation_id, model_id, rating, feedback_text, created_at }`
- [ ] `POST /v1/feedback` stores feedback
- [ ] `GET /v1/feedback?model_id=X` returns feedback summary per model
- [ ] Feedback visible in stats page: satisfaction rate per model

**Technical Notes:**
- Create `feedback` table: id, user_id, message_id, conversation_id, model_id, rating (1-5 or thumbs), feedback_text, created_at
- File: create `backend/app/routes/feedback.py`
- Frontend: add rating buttons to message component in chat page
- Add Alembic migration

**Complexity:** Medium

---

### Story 12.2: Routing Rule Auto-Tuning

**As a** user, **I want** the router to automatically improve based on my feedback **so that** I get better model selections over time.

**Acceptance Criteria:**
- [ ] After N feedback entries (configurable, default 20), system analyzes patterns
- [ ] Analysis identifies: which models get good ratings for which task types
- [ ] Routing rules updated: if model X gets 90%+ positive feedback for CODE tasks, prefer X for CODE
- [ ] Changes logged to `system_modifications` table with reason
- [ ] User can review and approve/reject auto-tuning suggestions
- [ ] `GET /v1/learning/suggestions` shows pending routing suggestions
- [ ] `POST /v1/learning/suggestions/{id}/apply` applies a suggestion

**Technical Notes:**
- File: create `backend/app/services/learning.py`
- Analysis: group feedback by (model_id, task_type), calculate satisfaction rate
- Task type from classifier output stored in request_logs
- Scheduled job: run analysis daily or on-demand
- Suggestions stored in new `learning_suggestions` table

**Complexity:** Large

---

### Story 12.3: Usage Pattern Recognition

**As a** user, **I want** the system to recognize my usage patterns **so that** it can proactively optimize.

**Acceptance Criteria:**
- [ ] System tracks: time-of-day usage, common task types, preferred models, session length
- [ ] Patterns surfaced in Settings: "You tend to use Claude for coding and Gemini for research"
- [ ] Proactive suggestions: "Based on your patterns, I recommend creating a persona for [use case]"
- [ ] `GET /v1/learning/patterns` returns detected patterns
- [ ] Privacy: user can opt out of pattern tracking in Settings
- [ ] Pattern data scoped per user, never shared

**Technical Notes:**
- File: extend `backend/app/services/learning.py`
- Pattern detection: aggregate request_logs by hour, day_of_week, task_type
- Store patterns: user preferences JSON or dedicated table
- Privacy flag: `user.preferences.pattern_tracking_enabled` (default true)

**Complexity:** Medium

---

### Story 12.4: Adaptive System Prompts

**As a** user, **I want** the system to adapt its prompts based on my preferences **so that** responses match my style.

**Acceptance Criteria:**
- [ ] System analyzes positive-rated responses for style patterns (length, formality, code style)
- [ ] Learned style preferences injected into system prompts: "User prefers concise responses with code examples"
- [ ] Style dimensions tracked: verbosity (concise/detailed), formality (casual/professional), code style (commented/minimal)
- [ ] User can view and edit learned style in Settings
- [ ] `GET /v1/learning/style` returns learned style profile
- [ ] `PATCH /v1/learning/style` allows manual override
- [ ] Style applied via memory context injection (existing infrastructure)

**Technical Notes:**
- Style analysis: sample 10 highest-rated responses, analyze common traits via LLM
- Inject as addition to system prompt: "Adapt your response style: [learned preferences]"
- File: extend `backend/app/services/memory_context.py`
- Update `identity_context.py` to include style preferences

**Complexity:** Large

---

## Appendix A: Story Dependency Map

```
E1 (Agent Execution) ← no dependencies
E2 (Parallel Execution) ← no dependencies
E3 (Conditional Branching) ← E2 (depends_on schema)
E4 (Visual Workflow Builder) ← E2, E3 (builder needs to support these)
E5 (Custom Templates) ← E4 (builder creates templates)
E6 (Analytics) ← no dependencies
E7 (OAuth & Auth) ← no dependencies
E8 (Real-time Collab) ← E7 (needs multi-user auth)
E9 (Voice) ← no dependencies
E10 (Production Deploy) ← no dependencies
E11 (Chat Self-Modification) ← no dependencies
E12 (Advanced Learning) ← E6 (needs analytics data)
```

## Appendix B: Complexity Legend

| Label | Estimate | Description |
|-------|----------|-------------|
| Small | 1-2 hours | Single file, straightforward logic |
| Medium | 3-6 hours | Multiple files, moderate logic, tests needed |
| Large | 8-16 hours | Cross-cutting concern, significant new infrastructure |

## Appendix C: Key File Reference

| Area | Backend Files | Frontend Files |
|------|--------------|----------------|
| Agents | `routes/agents.py`, `models/agent.py`, `schemas/agents.py` | `app/(main)/agents/` |
| Pipelines | `routes/pipelines.py`, `models/pipeline.py`, `services/phase_templates.py` | `app/(main)/workbench/pipelines/` |
| Chat | `routes/chat.py` | `app/chat/page.tsx` |
| Auth | `middleware/auth.py`, `routes/collaboration.py` | `app/auth/` |
| Stats | `routes/stats.py` | `app/(main)/stats/page.tsx` |
| Images | `routes/images.py` | `app/(main)/gallery/page.tsx` |
| Settings | — | `app/(main)/settings/page.tsx` |
| Models | `routes/models.py`, `models/model.py` | `app/(main)/models/page.tsx` |
