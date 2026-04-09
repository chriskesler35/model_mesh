# DevForgeAI Backend Data Models

> Comprehensive database schema reference for the DevForgeAI backend.
>
> **ORM**: SQLAlchemy 2.x (async)
> **Dev database**: SQLite (via aiosqlite)
> **Prod database**: PostgreSQL (via asyncpg)
> **Migrations**: Alembic + runtime ALTER TABLE helper (`app/migrate.py`)

---

## Table of Contents

1. [BaseMixin (shared columns)](#basemixin)
2. [UUIDType (cross-database compatibility)](#uuidtype)
3. [Provider (providers)](#1-provider)
4. [Model (models)](#2-model)
5. [Persona (personas)](#3-persona)
6. [Conversation (conversations)](#4-conversation)
7. [Message (messages)](#5-message)
8. [RequestLog (request_logs)](#6-requestlog)
9. [Agent (agents)](#7-agent)
10. [Task (tasks)](#8-task)
11. [WorkbenchSession (workbench_sessions)](#9-workbenchsession)
12. [Pipeline (workbench_pipelines)](#10-pipeline)
13. [PhaseRun (workbench_phase_runs)](#11-phaserun)
14. [CommandExecution (workbench_commands)](#12-commandexecution)
15. [Preference (preferences)](#13-preference)
16. [UserProfile (user_profiles)](#14-userprofile)
17. [MemoryFile (memory_files)](#15-memoryfile)
18. [PreferenceTracking (preference_tracking)](#16-preferencetracking)
19. [SystemModification (system_modifications)](#17-systemmodification)
20. [AppSetting (app_settings)](#18-appsetting)
21. [ER Diagram (relationships)](#er-diagram)
22. [Migration Strategy](#migration-strategy)

---

## BaseMixin

**Source**: `backend/app/models/base.py`

A mixin class applied to most ORM models (Provider, Model, Persona, Conversation, Message, RequestLog, Agent, Task, UserProfile, MemoryFile, PreferenceTracking, SystemModification). Provides three shared columns:

| Column       | Type                        | Constraints          | Notes                                      |
|--------------|-----------------------------|----------------------|--------------------------------------------|
| `id`         | `UUID` (PostgreSQL native)  | `PRIMARY KEY`        | Default: `uuid.uuid4()`                    |
| `created_at` | `DateTime`                  | `NOT NULL`           | Default: `datetime.utcnow`                 |
| `updated_at` | `DateTime`                  | `NOT NULL`           | Default: `datetime.utcnow`, auto on update |

Tables that do **not** use BaseMixin (they manage their own PK and timestamps): WorkbenchSession, Pipeline, PhaseRun, CommandExecution, Preference, AppSetting.

---

## UUIDType

**Source**: Defined locally in `conversation.py`, `request_log.py`, `task.py`, `preference.py`, `workbench.py`

A `TypeDecorator` wrapping `CHAR(36)` that stores UUIDs as 36-character strings for SQLite compatibility while remaining interoperable with PostgreSQL native UUIDs. Used wherever foreign keys reference UUID primary keys from SQLite-first tables.

```
impl = CHAR(36)
process_bind_param  -> str(value)
process_result_value -> uuid.UUID(str(value))
```

---

## 1. Provider

**Table**: `providers`
**Source**: `backend/app/models/provider.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

| Column         | Type           | Constraints                    | Default   | Notes                                    |
|----------------|----------------|--------------------------------|-----------|------------------------------------------|
| `id`           | `UUID`         | `PRIMARY KEY`                  | uuid4()   | From BaseMixin                           |
| `name`         | `String(100)`  | `UNIQUE`, `NOT NULL`, `INDEX`  |           | Internal slug: `ollama`, `anthropic`     |
| `display_name` | `String(200)`  |                                | `NULL`    | Human-readable label                     |
| `api_base_url` | `String(500)`  |                                | `NULL`    | Base URL for API calls                   |
| `auth_type`    | `String(50)`   |                                | `"none"`  | `bearer`, `api_key`, or `none`           |
| `config`       | `JSON`         |                                | `{}`      | Provider-specific configuration blob     |
| `is_active`    | `Boolean`      |                                | `True`    | Soft-delete / disable flag               |
| `created_at`   | `DateTime`     | `NOT NULL`                     | utcnow    | From BaseMixin                           |
| `updated_at`   | `DateTime`     | `NOT NULL`                     | utcnow    | From BaseMixin                           |

**Relationships**:
- `models` -- backref from Model (one-to-many)

**Indexes**:
- `ix_providers_name` on `name`

**Seed data** (from Alembic migration): `ollama`, `anthropic`, `google`

---

## 2. Model

**Table**: `models`
**Source**: `backend/app/models/model.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

| Column              | Type            | Constraints                                       | Default | Notes                                |
|---------------------|-----------------|---------------------------------------------------|---------|--------------------------------------|
| `id`                | `UUID`          | `PRIMARY KEY`                                     | uuid4() | From BaseMixin                       |
| `provider_id`       | `UUID`          | `FK -> providers.id ON DELETE CASCADE`, `NOT NULL` |         | Owning provider                      |
| `model_id`          | `String(200)`   | `NOT NULL`                                        |         | External model identifier            |
| `display_name`      | `String(200)`   |                                                   | `NULL`  | Human-readable name                  |
| `cost_per_1m_input` | `Numeric(10,6)` |                                                   | `0`     | Cost per 1M input tokens (USD)       |
| `cost_per_1m_output`| `Numeric(10,6)` |                                                   | `0`     | Cost per 1M output tokens (USD)      |
| `context_window`    | `Integer`       | `CHECK (context_window > 0 OR context_window IS NULL)` | `NULL` | Max context length in tokens    |
| `capabilities`      | `JSON`          |                                                   | `{}`    | Feature flags (vision, tools, etc.)  |
| `is_active`         | `Boolean`       |                                                   | `True`  | Soft-delete / disable flag           |
| `created_at`        | `DateTime`      | `NOT NULL`                                        | utcnow  | From BaseMixin                       |
| `updated_at`        | `DateTime`      | `NOT NULL`                                        | utcnow  | From BaseMixin                       |

**Relationships**:
- `provider` -- many-to-one -> Provider

**Table-level constraints**:
- `check_context_window_positive`: `context_window > 0 OR context_window IS NULL`
- `UNIQUE(provider_id, model_id)` (in Alembic migration)

---

## 3. Persona

**Table**: `personas`
**Source**: `backend/app/models/persona.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

| Column                | Type          | Constraints                                | Default   | Notes                                     |
|-----------------------|---------------|--------------------------------------------|-----------|-------------------------------------------|
| `id`                  | `UUID`        | `PRIMARY KEY`                              | uuid4()   | From BaseMixin                            |
| `name`                | `String(100)` | `UNIQUE`, `NOT NULL`, `INDEX`              |           | Persona slug                              |
| `description`         | `Text`        |                                            | `NULL`    | Brief description                         |
| `system_prompt`       | `Text`        |                                            | `NULL`    | System prompt injected into LLM calls     |
| `primary_model_id`    | `UUID`        | `FK -> models.id ON DELETE SET NULL`       | `NULL`    | Preferred model                           |
| `fallback_model_id`   | `UUID`        | `FK -> models.id ON DELETE SET NULL`       | `NULL`    | Fallback when primary unavailable         |
| `routing_rules`       | `JSON`        |                                            | `{}`      | Rules for dynamic model selection         |
| `memory_enabled`      | `Boolean`     |                                            | `True`    | Whether conversation memory is used       |
| `max_memory_messages` | `Integer`     |                                            | `10`      | Sliding window size for memory            |
| `is_default`          | `Boolean`     |                                            | `False`   | Whether this is the default persona       |
| `created_at`          | `DateTime`    | `NOT NULL`                                 | utcnow    | From BaseMixin                            |
| `updated_at`          | `DateTime`    |                                            | utcnow    | Overridden from BaseMixin with onupdate   |

**Relationships**:
- `primary_model` -- many-to-one -> Model (via `primary_model_id`)
- `fallback_model` -- many-to-one -> Model (via `fallback_model_id`)
- `conversations` -- backref from Conversation (one-to-many)

**Indexes**:
- `ix_personas_name` on `name`
- `ix_personas_default` partial index on `is_default` WHERE `is_default = true` (PostgreSQL only)

---

## 4. Conversation

**Table**: `conversations`
**Source**: `backend/app/models/conversation.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

| Column           | Type              | Constraints                               | Default | Notes                                        |
|------------------|-------------------|-------------------------------------------|---------|----------------------------------------------|
| `id`             | `UUID`            | `PRIMARY KEY`                             | uuid4() | From BaseMixin                               |
| `persona_id`     | `UUIDType`        | `FK -> personas.id ON DELETE SET NULL`    | `NULL`  | Active persona for this conversation         |
| `external_id`    | `String(100)`     | `UNIQUE`                                  | `NULL`  | External reference ID                        |
| `metadata`       | `JSON`            |                                           | `{}`    | Column aliased as `extra_data` in ORM        |
| `title`          | `String(200)`     |                                           | `NULL`  | Conversation title (auto or user-set)        |
| `pinned`         | `Boolean`         | `NOT NULL`                                | `False` | Pin to top of conversation list              |
| `keep_forever`   | `Boolean`         | `NOT NULL`                                | `False` | Exclude from auto-cleanup                    |
| `last_message_at`| `DateTime(tz)`    |                                           | `NULL`  | Timestamp of most recent message (tz-aware)  |
| `message_count`  | `Integer`         | `NOT NULL`                                | `0`     | Denormalized count of messages               |
| `created_at`     | `DateTime`        | `NOT NULL`                                | utcnow  | From BaseMixin                               |
| `updated_at`     | `DateTime`        | `NOT NULL`                                | utcnow  | From BaseMixin                               |

**Relationships**:
- `persona` -- many-to-one -> Persona
- `messages` -- one-to-many -> Message (cascade `all, delete-orphan`)

**Indexes**:
- `ix_conversations_persona` on `persona_id`

**Note**: The `metadata` column uses the ORM attribute name `extra_data` to avoid collision with SQLAlchemy's reserved `.metadata` attribute.

---

## 5. Message

**Table**: `messages`
**Source**: `backend/app/models/conversation.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

| Column            | Type            | Constraints                                        | Default | Notes                                   |
|-------------------|-----------------|----------------------------------------------------|---------|-----------------------------------------|
| `id`              | `UUID`          | `PRIMARY KEY`                                      | uuid4() | From BaseMixin                          |
| `conversation_id` | `UUIDType`      | `FK -> conversations.id ON DELETE CASCADE`, `NOT NULL`, `INDEX` | | Parent conversation              |
| `role`            | `String(20)`    | `NOT NULL`                                         |         | `user`, `assistant`, `system`, `tool`   |
| `content`         | `Text`          | `NOT NULL`                                         |         | Message body (markdown)                 |
| `image_url`       | `Text`          |                                                    | `NULL`  | URL of inline generated image           |
| `model_used`      | `UUIDType`      | `FK -> models.id ON DELETE SET NULL`               | `NULL`  | Which model generated this response     |
| `tokens_in`       | `Integer`       |                                                    | `NULL`  | Input token count                       |
| `tokens_out`      | `Integer`       |                                                    | `NULL`  | Output token count                      |
| `latency_ms`      | `Integer`       |                                                    | `NULL`  | Round-trip latency in milliseconds      |
| `estimated_cost`  | `Numeric(10,6)` |                                                    | `0`     | Estimated cost in USD                   |
| `created_at`      | `DateTime`      | `NOT NULL`                                         | utcnow  | From BaseMixin                          |
| `updated_at`      | `DateTime`      | `NOT NULL`                                         | utcnow  | From BaseMixin                          |

**Relationships**:
- `conversation` -- many-to-one -> Conversation
- `model` -- many-to-one -> Model

**Indexes**:
- `idx_messages_conversation` composite on `(conversation_id, created_at DESC)`

---

## 6. RequestLog

**Table**: `request_logs`
**Source**: `backend/app/models/request_log.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

| Column            | Type            | Constraints                                  | Default | Notes                                |
|-------------------|-----------------|----------------------------------------------|---------|--------------------------------------|
| `id`              | `UUID`          | `PRIMARY KEY`                                | uuid4() | From BaseMixin                       |
| `conversation_id` | `UUIDType`      | `FK -> conversations.id ON DELETE SET NULL`  | `NULL`  | Linked conversation                  |
| `persona_id`      | `UUIDType`      | `FK -> personas.id ON DELETE SET NULL`       | `NULL`  | Persona used                         |
| `model_id`        | `UUIDType`      | `FK -> models.id ON DELETE SET NULL`         | `NULL`  | Model used                           |
| `provider_id`     | `UUIDType`      | `FK -> providers.id ON DELETE SET NULL`      | `NULL`  | Provider used                        |
| `input_tokens`    | `Integer`       |                                              | `NULL`  | Input token count                    |
| `output_tokens`   | `Integer`       |                                              | `NULL`  | Output token count                   |
| `latency_ms`      | `Integer`       |                                              | `NULL`  | Latency in milliseconds              |
| `estimated_cost`  | `Numeric(10,6)` |                                              | `0`     | Estimated cost in USD                |
| `success`         | `Boolean`       |                                              | `NULL`  | Whether the request succeeded        |
| `error_message`   | `Text`          |                                              | `NULL`  | Sanitized error (no sensitive data)  |
| `created_at`      | `DateTime`      | `NOT NULL`                                   | utcnow  | From BaseMixin                       |
| `updated_at`      | `DateTime`      | `NOT NULL`                                   | utcnow  | From BaseMixin                       |

**Indexes**:
- `idx_request_logs_created_at` on `created_at DESC`

---

## 7. Agent

**Table**: `agents`
**Source**: `backend/app/models/agent.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

| Column            | Type          | Constraints    | Default | Notes                                              |
|-------------------|---------------|----------------|---------|----------------------------------------------------|
| `id`              | `UUID`        | `PRIMARY KEY`  | uuid4() | From BaseMixin                                     |
| `name`            | `String(255)` | `NOT NULL`     |         | Agent name (`Coder`, `Researcher`, etc.)           |
| `agent_type`      | `String(50)`  | `NOT NULL`     |         | Type slug: `coder`, `researcher`, `designer`, etc. |
| `description`     | `Text`        |                | `NULL`  | Brief description of purpose                       |
| `system_prompt`   | `Text`        | `NOT NULL`     |         | System prompt for LLM calls                        |
| `model_id`        | `UUID`        |                | `NULL`  | Direct model override (optional)                   |
| `persona_id`      | `UUID`        |                | `NULL`  | Persona to use (model resolved through persona)    |
| `method_phase`    | `String(50)`  | `INDEX`        | `NULL`  | Pipeline phase this agent serves (e.g. `Coder`)    |
| `tools`           | `JSON`        |                | `[]`    | List of tool names: `read_file`, `shell_execute`   |
| `memory_enabled`  | `Boolean`     |                | `True`  | Whether agent retains memory across iterations     |
| `max_iterations`  | `Integer`     |                | `10`    | Maximum tool-use loop iterations                   |
| `timeout_seconds` | `Integer`     |                | `300`   | Hard timeout for agent execution                   |
| `is_active`       | `Boolean`     |                | `True`  | Soft-delete / disable flag                         |
| `user_id`         | `UUID`        |                | `NULL`  | Owner user ID                                      |
| `created_at`      | `DateTime`    | `NOT NULL`     | utcnow  | From BaseMixin                                     |
| `updated_at`      | `DateTime`    | `NOT NULL`     | utcnow  | From BaseMixin                                     |

**Note**: `model_id` and `persona_id` are stored as raw `UUID` columns without FK constraints (soft references). The Agent model also includes `DEFAULT_AGENTS` -- a Python list of seven seed agent configurations (Coder, Researcher, Designer, Reviewer, Planner, Executor, Writer).

---

## 8. Task

**Table**: `tasks`
**Source**: `backend/app/models/task.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

| Column            | Type          | Constraints   | Default     | Notes                                       |
|-------------------|---------------|---------------|-------------|---------------------------------------------|
| `id`              | `UUID`        | `PRIMARY KEY` | uuid4()     | From BaseMixin                              |
| `task_type`       | `String(50)`  | `NOT NULL`    |             | `image_gen`, `agent_run`, etc.              |
| `status`          | `String(20)`  | `NOT NULL`    | `"pending"` | `pending`, `running`, `completed`, `failed` |
| `params`          | `JSON`        |               | `{}`        | Input parameters (prompt, model, etc.)      |
| `result`          | `JSON`        |               | `NULL`      | Output data (image URL, etc.)               |
| `error`           | `Text`        |               | `NULL`      | Error message if failed                     |
| `progress`        | `Integer`     |               | `0`         | Percentage complete: 0-100                  |
| `user_message`    | `String(500)` |               | `NULL`      | Human-readable status message               |
| `conversation_id` | `String(36)`  |               | `NULL`      | Link back to originating conversation       |
| `acknowledged`    | `Integer`     |               | `0`         | `0` = unread, `1` = seen by user            |
| `created_at`      | `DateTime`    | `NOT NULL`    | utcnow      | From BaseMixin                              |
| `updated_at`      | `DateTime`    | `NOT NULL`    | utcnow      | From BaseMixin                              |

---

## 9. WorkbenchSession

**Table**: `workbench_sessions`
**Source**: `backend/app/models/workbench.py`
**Mixin**: None (manages its own columns)

| Column             | Type            | Constraints   | Default        | Notes                                         |
|--------------------|-----------------|---------------|----------------|-----------------------------------------------|
| `id`               | `CHAR(36)`      | `PRIMARY KEY` | uuid4() as str | String UUID                                   |
| `task`             | `Text`          | `NOT NULL`    |                | Task description / user prompt                |
| `agent_type`       | `String(50)`    |               | `"coder"`      | Agent type slug                               |
| `model`            | `String(200)`   |               | `NULL`         | Model identifier string                       |
| `project_id`       | `CHAR(36)`      |               | `NULL`         | Linked project ID                             |
| `project_path`     | `Text`          |               | `NULL`         | Filesystem path for project workspace         |
| `pipeline_id`      | `CHAR(36)`      | `INDEX`       | `NULL`         | Link to active pipeline (Option A)            |
| `status`           | `String(20)`    |               | `"pending"`    | `pending`, `running`, `completed`, `failed`, `cancelled` |
| `files`            | `JSON`          |               | `[]`           | List of relative file paths written           |
| `events_log`       | `JSON`          |               | `[]`           | All SSE events for replay on reconnect        |
| `messages`         | `JSON`          |               | `[]`           | Conversation history `[{role, content}]`      |
| `input_tokens`     | `Integer`       |               | `NULL`         | Total input tokens consumed                   |
| `output_tokens`    | `Integer`       |               | `NULL`         | Total output tokens consumed                  |
| `estimated_cost`   | `Numeric(10,6)` |               | `NULL`         | Estimated total cost in USD                   |
| `bypass_approvals` | `Boolean`       | `NOT NULL`    | `False`        | YOLO mode: skip all command approval gates    |
| `created_at`       | `DateTime`      |               | `func.now()`   | Server-side default                           |
| `started_at`       | `DateTime`      |               | `NULL`         | When execution began                          |
| `completed_at`     | `DateTime`      |               | `NULL`         | When execution finished                       |

**Relationships** (via FK from child tables):
- Pipeline.session_id -> WorkbenchSession.id
- CommandExecution.session_id -> WorkbenchSession.id

---

## 10. Pipeline

**Table**: `workbench_pipelines`
**Source**: `backend/app/models/pipeline.py`
**Mixin**: None

| Column                | Type          | Constraints                                              | Default     | Notes                                              |
|-----------------------|---------------|----------------------------------------------------------|-------------|----------------------------------------------------|
| `id`                  | `CHAR(36)`    | `PRIMARY KEY`                                            | uuid4()     |                                                    |
| `session_id`          | `CHAR(36)`    | `FK -> workbench_sessions.id ON DELETE CASCADE`, `NOT NULL` |          | Parent session                                     |
| `method_id`           | `String(50)`  | `NOT NULL`                                               |             | Pipeline method: `bmad`, `gsd`, `superpowers`      |
| `phases`              | `JSON`        | `NOT NULL`                                               |             | Array of phase definitions `[{name, role, model, system_prompt, artifact_type}]` |
| `current_phase_index` | `Integer`     | `NOT NULL`                                               | `0`         | Zero-based index of current phase                  |
| `status`              | `String(30)`  |                                                          | `"pending"` | `pending`, `running`, `awaiting_approval`, `completed`, `failed`, `cancelled` |
| `auto_approve`        | `Boolean`     | `NOT NULL`                                               | `False`     | Skip approval gates between phases                 |
| `initial_task`        | `Text`        | `NOT NULL`                                               |             | Original user task passed to the pipeline          |
| `created_at`          | `DateTime`    |                                                          | `func.now()`|                                                    |
| `completed_at`        | `DateTime`    |                                                          | `NULL`      |                                                    |

**Relationships**:
- PhaseRun.pipeline_id -> Pipeline.id

---

## 11. PhaseRun

**Table**: `workbench_phase_runs`
**Source**: `backend/app/models/pipeline.py`
**Mixin**: None

| Column            | Type          | Constraints                                               | Default     | Notes                                               |
|-------------------|---------------|-----------------------------------------------------------|-------------|-----------------------------------------------------|
| `id`              | `CHAR(36)`    | `PRIMARY KEY`                                             | uuid4()     |                                                     |
| `pipeline_id`     | `CHAR(36)`    | `FK -> workbench_pipelines.id ON DELETE CASCADE`, `NOT NULL` |          | Parent pipeline                                     |
| `phase_index`     | `Integer`     | `NOT NULL`                                                |             | Zero-based position in pipeline                     |
| `phase_name`      | `String(100)` | `NOT NULL`                                                |             | Human name: `Analysis`, `Architecture`, etc.        |
| `agent_role`      | `String(100)` | `NOT NULL`                                                |             | `Business Analyst`, `Architect`, `Coder`, etc.      |
| `model_id`        | `String(200)` |                                                           | `NULL`      | Model identifier override for this phase            |
| `status`          | `String(30)`  |                                                           | `"pending"` | `pending`, `running`, `awaiting_approval`, `approved`, `rejected`, `failed`, `skipped` |
| `input_context`   | `JSON`        |                                                           | `NULL`      | Artifacts from prior phases passed as input         |
| `output_artifact` | `JSON`        |                                                           | `NULL`      | Structured output produced by this phase            |
| `raw_response`    | `Text`        |                                                           | `NULL`      | Full unprocessed LLM response text                  |
| `user_feedback`   | `Text`        |                                                           | `NULL`      | Feedback provided when user rejects phase output    |
| `input_tokens`    | `Integer`     |                                                           | `NULL`      | Input tokens consumed                               |
| `output_tokens`   | `Integer`     |                                                           | `NULL`      | Output tokens consumed                              |
| `started_at`      | `DateTime`    |                                                           | `NULL`      | When phase execution began                          |
| `completed_at`    | `DateTime`    |                                                           | `NULL`      | When phase execution finished                       |
| `created_at`      | `DateTime`    |                                                           | `func.now()`|                                                     |

---

## 12. CommandExecution

**Table**: `workbench_commands`
**Source**: `backend/app/models/command_execution.py`
**Mixin**: None

Audit record for every `CMD:` block emitted by a workbench agent.

| Column          | Type          | Constraints                                              | Default     | Notes                                                |
|-----------------|---------------|----------------------------------------------------------|-------------|------------------------------------------------------|
| `id`            | `CHAR(36)`    | `PRIMARY KEY`                                            | uuid4()     |                                                      |
| `session_id`    | `CHAR(36)`    | `FK -> workbench_sessions.id ON DELETE CASCADE`, `NOT NULL`, `INDEX` |  | Parent session                                       |
| `pipeline_id`   | `CHAR(36)`    | `INDEX`                                                  | `NULL`      | Set when emitted from a pipeline phase               |
| `phase_run_id`  | `CHAR(36)`    | `INDEX`                                                  | `NULL`      | Set when emitted from a pipeline phase               |
| `turn_number`   | `Integer`     |                                                          | `NULL`      | Conversation turn that triggered this command         |
| `command`       | `Text`        | `NOT NULL`                                               |             | The shell command string                             |
| `tier`          | `String(20)`  | `NOT NULL`                                               |             | `auto`, `notice`, `approval`, `blocked`              |
| `status`        | `String(20)`  | `NOT NULL`                                               | `"pending"` | `pending`, `approved`, `rejected`, `running`, `completed`, `failed`, `skipped`, `bypassed` |
| `exit_code`     | `Integer`     |                                                          | `NULL`      | Process exit code                                    |
| `stdout`        | `Text`        |                                                          | `NULL`      | Captured standard output (truncated)                 |
| `stderr`        | `Text`        |                                                          | `NULL`      | Captured standard error (truncated)                  |
| `user_feedback` | `Text`        |                                                          | `NULL`      | Reason provided when user rejects a command          |
| `bypass_used`   | `Boolean`     | `NOT NULL`                                               | `False`     | True if executed via bypass (YOLO) mode              |
| `duration_ms`   | `Integer`     |                                                          | `NULL`      | Execution wall-clock time in milliseconds            |
| `created_at`    | `DateTime`    |                                                          | `func.now()`|                                                      |
| `started_at`    | `DateTime`    |                                                          | `NULL`      |                                                      |
| `completed_at`  | `DateTime`    |                                                          | `NULL`      |                                                      |

**Indexes**:
- `idx_workbench_commands_session` on `session_id`
- `idx_workbench_commands_pipeline` on `pipeline_id`
- `idx_workbench_commands_status` on `status` (SQLite migration only)

---

## 13. Preference

**Table**: `preferences`
**Source**: `backend/app/models/preference.py`
**Mixin**: None

Stores learned user preferences detected from chat interactions.

| Column       | Type          | Constraints   | Default       | Notes                                          |
|--------------|---------------|---------------|---------------|------------------------------------------------|
| `id`         | `CHAR(36)`    | `PRIMARY KEY` | uuid4()       |                                                |
| `key`        | `String(200)` | `NOT NULL`    |               | Preference key: `coding_style`, `response_format` |
| `value`      | `Text`        | `NOT NULL`    |               | Preference description or value                |
| `category`   | `String(100)` |               | `"general"`   | `general`, `coding`, `communication`, `ui`, `workflow` |
| `source`     | `String(50)`  |               | `"detected"`  | `detected` (from chat) or `manual` (user-set)  |
| `is_active`  | `Boolean`     |               | `True`        | User can toggle off without deleting           |
| `created_at` | `DateTime`    |               | `func.now()`  | Server-side default                            |
| `updated_at` | `DateTime`    |               | `func.now()`  | Auto-updated on change                         |

---

## 14. UserProfile

**Table**: `user_profiles`
**Source**: `backend/app/models/user_profile.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

| Column        | Type          | Constraints   | Default    | Notes                                      |
|---------------|---------------|---------------|------------|--------------------------------------------|
| `id`          | `UUID`        | `PRIMARY KEY` | uuid4()    | From BaseMixin                             |
| `name`        | `String(255)` | `NOT NULL`    | `"User"`   | Display name                               |
| `email`       | `String(255)` |               | `NULL`     | Email address                              |
| `preferences` | `JSON`        |               | `{}`       | Structured prefs: `{tone, verbosity, ...}` |
| `is_active`   | `Boolean`     |               | `True`     | Soft-delete flag                           |
| `created_at`  | `DateTime`    | `NOT NULL`    | utcnow     | From BaseMixin                             |
| `updated_at`  | `DateTime`    | `NOT NULL`    | utcnow     | From BaseMixin                             |

**Relationships** (via FK from child tables):
- MemoryFile.user_id -> UserProfile.id
- PreferenceTracking.user_id -> UserProfile.id
- SystemModification.user_id -> UserProfile.id

---

## 15. MemoryFile

**Table**: `memory_files`
**Source**: `backend/app/models/user_profile.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

Stores persistent memory documents like `USER.md`, `CONTEXT.md`, `PREFERENCES.md`.

| Column        | Type          | Constraints                                   | Default | Notes                         |
|---------------|---------------|-----------------------------------------------|---------|-------------------------------|
| `id`          | `UUID`        | `PRIMARY KEY`                                 | uuid4() | From BaseMixin                |
| `user_id`     | `UUID`        | `FK -> user_profiles.id ON DELETE CASCADE`    |         | Owning user                   |
| `name`        | `String(255)` | `NOT NULL`                                    |         | File name: `USER.md`, etc.    |
| `content`     | `Text`        | `NOT NULL`                                    | `""`    | File content (markdown)       |
| `description` | `String(500)` |                                               | `NULL`  | Brief description of purpose  |
| `created_at`  | `DateTime`    | `NOT NULL`                                    | utcnow  | From BaseMixin                |
| `updated_at`  | `DateTime`    | `NOT NULL`                                    | utcnow  | From BaseMixin                |

**Indexes**:
- `ix_memory_files_user_id` on `user_id`

---

## 16. PreferenceTracking

**Table**: `preference_tracking`
**Source**: `backend/app/models/user_profile.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

Tracks learned preferences from chat interactions, with confidence scoring.

| Column       | Type          | Constraints                                   | Default    | Notes                                     |
|--------------|---------------|-----------------------------------------------|------------|-------------------------------------------|
| `id`         | `UUID`        | `PRIMARY KEY`                                 | uuid4()    | From BaseMixin                            |
| `user_id`    | `UUID`        | `FK -> user_profiles.id ON DELETE CASCADE`    |            | Owning user                               |
| `key`        | `String(255)` | `NOT NULL`                                    |            | `preferred_language`, `coding_style`, etc.|
| `value`      | `Text`        | `NOT NULL`                                    |            | The learned value                         |
| `source`     | `String(50)`  | `NOT NULL`                                    |            | `chat`, `manual`, `system`                |
| `confidence` | `String(20)`  |                                               | `"medium"` | `low`, `medium`, `high`                   |
| `context`    | `Text`        |                                               | `NULL`     | Conversation context where learned        |
| `created_at` | `DateTime`    | `NOT NULL`                                    | utcnow     | From BaseMixin                            |
| `updated_at` | `DateTime`    | `NOT NULL`                                    | utcnow     | From BaseMixin                            |

**Indexes**:
- `ix_preference_tracking_user_id` on `user_id`
- `ix_preference_tracking_key` on `key`

---

## 17. SystemModification

**Table**: `system_modifications`
**Source**: `backend/app/models/user_profile.py`
**Mixin**: BaseMixin (id, created_at, updated_at)

Audit log of system modifications made through chat (model additions, persona updates, etc.).

| Column              | Type          | Constraints                                            | Default | Notes                                         |
|---------------------|---------------|--------------------------------------------------------|---------|-----------------------------------------------|
| `id`                | `UUID`        | `PRIMARY KEY`                                          | uuid4() | From BaseMixin                                |
| `user_id`           | `UUID`        | `FK -> user_profiles.id ON DELETE CASCADE`             |         | User who made the modification                |
| `conversation_id`   | `UUID`        | `FK -> conversations.id ON DELETE SET NULL`            | `NULL`  | Conversation where modification was requested |
| `modification_type` | `String(50)`  | `NOT NULL`                                             |         | `add_model`, `update_persona`, etc.           |
| `entity_type`       | `String(50)`  | `NOT NULL`                                             |         | `model`, `persona`, `memory_file`             |
| `entity_id`         | `UUID`        |                                                        | `NULL`  | ID of the entity that was modified            |
| `before_value`      | `JSON`        |                                                        | `NULL`  | Snapshot of entity state before change        |
| `after_value`       | `JSON`        |                                                        | `NULL`  | Snapshot of entity state after change         |
| `reason`            | `Text`        |                                                        | `NULL`  | Why this change was made                      |
| `created_at`        | `DateTime`    | `NOT NULL`                                             | utcnow  | From BaseMixin                                |
| `updated_at`        | `DateTime`    | `NOT NULL`                                             | utcnow  | From BaseMixin                                |

**Indexes**:
- `ix_system_modifications_user_id` on `user_id`

---

## 18. AppSetting

**Table**: `app_settings`
**Source**: `backend/app/models/app_settings.py`
**Mixin**: None

Simple key-value store for application-level configuration.

| Column       | Type          | Constraints   | Default      | Notes                        |
|--------------|---------------|---------------|--------------|------------------------------|
| `key`        | `String(200)` | `PRIMARY KEY` |              | Setting key                  |
| `value`      | `Text`        |               | `NULL`       | Setting value (serialized)   |
| `updated_at` | `DateTime`    |               | `func.now()` | Auto-updated on change       |

---

## ER Diagram

Below is a textual entity-relationship diagram showing all foreign-key relationships in the schema.

```
Provider (providers)
  |
  | 1:N  provider_id (CASCADE)
  v
Model (models)
  |
  |--- 1:N  primary_model_id (SET NULL) ---> Persona (personas)
  |--- 1:N  fallback_model_id (SET NULL) --> Persona (personas)
  |--- 1:N  model_used (SET NULL) ---------> Message (messages)
  |--- 1:N  model_id (SET NULL) -----------> RequestLog (request_logs)
  |
  v
Persona (personas)
  |
  | 1:N  persona_id (SET NULL)
  v
Conversation (conversations)
  |
  | 1:N  conversation_id (CASCADE)
  v
Message (messages)


UserProfile (user_profiles)
  |
  |--- 1:N  user_id (CASCADE) ---> MemoryFile (memory_files)
  |--- 1:N  user_id (CASCADE) ---> PreferenceTracking (preference_tracking)
  |--- 1:N  user_id (CASCADE) ---> SystemModification (system_modifications)

SystemModification
  |--- N:1  conversation_id (SET NULL) ---> Conversation

RequestLog (request_logs)
  |--- N:1  conversation_id (SET NULL) ---> Conversation
  |--- N:1  persona_id (SET NULL) -------> Persona
  |--- N:1  model_id (SET NULL) ---------> Model
  |--- N:1  provider_id (SET NULL) ------> Provider


WorkbenchSession (workbench_sessions)
  |
  |--- 1:N  session_id (CASCADE) ---> Pipeline (workbench_pipelines)
  |--- 1:N  session_id (CASCADE) ---> CommandExecution (workbench_commands)
  |
  v
Pipeline (workbench_pipelines)
  |
  | 1:N  pipeline_id (CASCADE)
  v
PhaseRun (workbench_phase_runs)


Standalone tables (no FK relationships):
  - Agent (agents)          -- model_id and persona_id are soft references (no FK constraint)
  - Task (tasks)            -- conversation_id is a plain String(36), no FK constraint
  - Preference (preferences)
  - AppSetting (app_settings)
```

### Relationship Summary

| Parent               | Child               | FK Column            | On Delete    | Cardinality |
|----------------------|---------------------|----------------------|--------------|-------------|
| Provider             | Model               | `provider_id`        | `CASCADE`    | 1:N         |
| Model                | Persona             | `primary_model_id`   | `SET NULL`   | 1:N         |
| Model                | Persona             | `fallback_model_id`  | `SET NULL`   | 1:N         |
| Model                | Message             | `model_used`         | `SET NULL`   | 1:N         |
| Model                | RequestLog          | `model_id`           | `SET NULL`   | 1:N         |
| Persona              | Conversation        | `persona_id`         | `SET NULL`   | 1:N         |
| Conversation         | Message             | `conversation_id`    | `CASCADE`    | 1:N         |
| Conversation         | RequestLog          | `conversation_id`    | `SET NULL`   | 1:N         |
| Conversation         | SystemModification  | `conversation_id`    | `SET NULL`   | 1:N         |
| Persona              | RequestLog          | `persona_id`         | `SET NULL`   | 1:N         |
| Provider             | RequestLog          | `provider_id`        | `SET NULL`   | 1:N         |
| UserProfile          | MemoryFile          | `user_id`            | `CASCADE`    | 1:N         |
| UserProfile          | PreferenceTracking  | `user_id`            | `CASCADE`    | 1:N         |
| UserProfile          | SystemModification  | `user_id`            | `CASCADE`    | 1:N         |
| WorkbenchSession     | Pipeline            | `session_id`         | `CASCADE`    | 1:N         |
| WorkbenchSession     | CommandExecution    | `session_id`         | `CASCADE`    | 1:N         |
| Pipeline             | PhaseRun            | `pipeline_id`        | `CASCADE`    | 1:N         |

---

## Migration Strategy

The project uses a dual migration approach to support both PostgreSQL (production) and SQLite (development) simultaneously.

### 1. Alembic Migrations (PostgreSQL)

**Location**: `backend/alembic/versions/`

These are standard Alembic revisions targeting PostgreSQL with native types.

#### `001_initial_schema.py`

- Creates the core tables: `providers`, `models`, `personas`, `conversations`, `messages`, `request_logs`
- Enables the `uuid-ossp` PostgreSQL extension for server-side UUID generation
- Uses `postgresql.UUID(as_uuid=True)` for primary keys
- Uses `postgresql.JSONB` for JSON columns (indexed, queryable)
- Creates covering indexes on frequently queried columns
- Seeds three default providers: `ollama`, `anthropic`, `google`
- Adds a composite unique constraint on `(provider_id, model_id)` in the models table
- Creates a partial index on `personas.is_default` (PostgreSQL-specific `WHERE is_default = true`)

#### `add_user_profile.py`

- Creates the user personalization tables: `user_profiles`, `memory_files`, `preference_tracking`, `system_modifications`
- Adds covering indexes for user_id lookups on all child tables
- Adds a key index on `preference_tracking.key`

### 2. Runtime Migrations (SQLite)

**Location**: `backend/app/migrate.py`

Since SQLite does not support `ALTER TABLE ... ADD COLUMN` with all constraint types and has no native `JSONB` or `UUID`, a runtime migration system handles schema evolution for the development database.

**How it works**:
1. On application startup, `run_migrations()` is called.
2. Each SQL statement in the `MIGRATIONS` list is executed inside a transaction.
3. "Duplicate column" errors are silently ignored, making migrations idempotent.
4. Other errors are logged as warnings but do not crash the application.

**Migrations handled at runtime**:

| Target Table          | Change                                                     |
|-----------------------|------------------------------------------------------------|
| `agents`              | Add `persona_id VARCHAR(36)` column                       |
| `agents`              | Add `method_phase VARCHAR(50)` column                     |
| `conversations`       | Add `title VARCHAR(200)` column                           |
| `conversations`       | Add `pinned BOOLEAN NOT NULL DEFAULT 0` column            |
| `conversations`       | Add `keep_forever BOOLEAN NOT NULL DEFAULT 0` column      |
| `conversations`       | Add `last_message_at DATETIME` column                     |
| `conversations`       | Add `message_count INTEGER NOT NULL DEFAULT 0` column     |
| `workbench_sessions`  | Add `input_tokens INTEGER` column                         |
| `workbench_sessions`  | Add `output_tokens INTEGER` column                        |
| `workbench_sessions`  | Add `estimated_cost NUMERIC(10,6)` column                 |
| `workbench_sessions`  | Add `events_log JSON` column                              |
| `workbench_sessions`  | Add `messages JSON` column                                |
| `workbench_sessions`  | Add `pipeline_id VARCHAR(36)` column                      |
| `workbench_sessions`  | Add `bypass_approvals BOOLEAN NOT NULL DEFAULT 0` column  |
| `workbench_commands`  | Full `CREATE TABLE IF NOT EXISTS` (table created at runtime) |
| `workbench_commands`  | Indexes on `session_id`, `pipeline_id`, `status`          |
| `messages`            | Add `image_url TEXT` column                               |

### 3. SQLAlchemy `create_all`

Tables that do not appear in any Alembic migration (such as `workbench_sessions`, `workbench_pipelines`, `workbench_phase_runs`, `tasks`, `agents`, `preferences`, `app_settings`) are created by SQLAlchemy's `Base.metadata.create_all()` during application startup. This call is a no-op for tables that already exist.

### Migration Execution Order

1. `Base.metadata.create_all()` -- ensures all tables exist with current ORM definitions
2. `run_migrations()` from `app/migrate.py` -- adds columns that may be missing on existing SQLite databases
3. Alembic (PostgreSQL only, run manually) -- `alembic upgrade head`
