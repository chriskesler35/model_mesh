# Integration Architecture

## Overview

DevForgeAI is a multi-part application with a Python FastAPI backend serving as the central hub, a Next.js frontend as the primary web UI, and a VS Code extension for IDE integration. All three parts communicate through the backend's OpenAI-compatible REST API and Server-Sent Events (SSE) streams.

---

## Backend -> Frontend Communication

### REST API

The frontend calls the backend REST API at port 19000. The base URL is auto-detected from `window.location.hostname`, allowing the frontend to work in both local development and Docker environments without hardcoded URLs.

### Authentication

All requests carry a Bearer token in the `Authorization` header. Tokens are either:

- **JWT** issued by the `/v1/auth/login` endpoint (for multi-user deployments)
- **Master API key** `modelmesh_local_dev_key` (for single-user local development)

### Real-Time Streaming (SSE)

Server-Sent Events are used for all real-time communication:

- **Chat completions** (`POST /v1/chat/completions` with `stream: true`) -- token-by-token LLM output
- **Workbench events** (`GET /v1/workbench/sessions/{id}/events`) -- tool calls, command output, file edits, LLM turns
- **Pipeline events** (`GET /v1/pipelines/{id}/events`) -- phase transitions, approval gates, agent output
- **Project runner output** (`GET /v1/projects/{id}/runner/events`) -- sandbox command execution results

### Next.js API Routes

The frontend also exposes server-side API routes for operations that should not run in the browser:

- `/api/backend` -- proxy requests to the backend (useful when CORS is restrictive)
- `/api/health` -- frontend health check endpoint
- `/api/readme` -- serves project README content

---

## Backend -> Extension Communication

### REST API

The VS Code extension calls the backend at a configurable URL. The default is `http://localhost:18800/v1`, but users can change this in VS Code settings (`modelMesh.apiUrl`).

### Authentication

The extension sends a Bearer token from VS Code settings (`modelMesh.apiKey`). The default value is `modelmesh_local_dev_key`.

### Endpoints Used

The extension uses a minimal API surface:

- `POST /v1/chat/completions` -- send code selections or questions to the LLM (supports both streaming and non-streaming responses)
- `GET /v1/personas` -- fetch available personas for the TreeView sidebar panel

---

## Data Flow Patterns

### 1. Chat Completion

```
User -> Frontend/Extension
  -> POST /v1/chat/completions
    -> Router
      -> PersonaResolver (select model based on persona + task type)
        -> ModelClient
          -> LiteLLM
            -> Provider API (Ollama, Anthropic, Google, OpenRouter, OpenAI, etc.)
              -> SSE stream back to caller
```

The persona resolver picks the appropriate model and provider based on the selected persona's configuration, including fallback chains if the primary model is unavailable.

### 2. Workbench (Single-Agent)

```
User -> Frontend
  -> POST /v1/workbench/sessions (create session with goal)
    -> Backend spawns LLM turns with tool use
      -> Tools: file read/write, command execution, web search, image generation
        -> SSE events stream back (tool_call, tool_result, assistant_message, etc.)
          -> Frontend renders conversation + artifacts
```

The workbench runs an agentic loop where the LLM can invoke tools, observe results, and continue reasoning until the goal is met or the user intervenes.

### 3. Pipeline (Multi-Agent)

```
User -> Frontend
  -> POST /v1/pipelines (create pipeline from template: BMAD, GSD, SuperPowers)
    -> Backend runs phases sequentially
      -> Each phase: select agent persona -> run LLM with phase prompt -> produce artifact
        -> SSE events stream back (phase_start, phase_complete, approval_requested, etc.)
          -> Approval gates pause execution until user approves
            -> Frontend swim-lane UI shows all phases and their status
```

Pipelines support per-phase model overrides, retry on failure, and approval gates between phases.

### 4. Image Generation

```
User -> Frontend
  -> POST /v1/tasks (type: image_gen, prompt, parameters)
    -> Backend
      -> Route to provider:
        -> Gemini Imagen API (cloud)
        -> ComfyUI (local, 6 workflow templates)
      -> Task enters "pending" state
        -> Frontend polls GET /v1/tasks/{id} for completion
          -> On completion: image URL returned, displayed inline
```

---

## Shared Resources

### SQLite Database

`data/devforgeai.db` is the single source of truth for all persistent state: conversations, personas, models, providers, projects, workbench sessions, pipelines, tasks, users, API keys, and usage tracking. PostgreSQL is used in Docker deployments.

### Data Directory

The `data/` directory contains runtime files shared across backend processes:

- **Identity files**: `soul.md`, `user.md`, `identity.md` -- AI personality and user context
- **Context snapshots**: project state captures for rollback
- **Images**: generated images stored locally
- **Workflows**: ComfyUI workflow JSON templates
- **State files**: pipeline state, session state

### Environment Variables

The `.env` file in the project root contains API keys and configuration shared between backend processes. Keys include provider credentials (Anthropic, Google, OpenRouter, OpenAI), database URLs, Redis URLs, and feature flags.

### Redis (Optional)

When available, Redis provides:

- **Conversation memory cache** -- faster retrieval of recent conversation context
- **Rate limiting** -- per-key request throttling via the rate limit middleware

---

## Port Mapping

| Service     | Local Development | Docker        | Notes                          |
|-------------|-------------------|---------------|--------------------------------|
| Backend     | 19000             | 18800         | FastAPI with uvicorn           |
| Frontend    | 3001              | 18801         | Next.js dev server / standalone|
| PostgreSQL  | --                | 15432         | Docker only                    |
| Redis       | --                | 16379         | Docker only (optional locally) |
| Ollama      | 11434             | 11434         | Local LLM inference            |
| ComfyUI     | 8188              | 8188          | Local image generation         |

---

## Error Handling and Resilience

- **Fallback chains**: If a model or provider is unavailable, the persona resolver tries the next model in the fallback chain
- **SSE reconnection**: The frontend automatically reconnects SSE streams on disconnect, replaying missed events
- **Self-healing snapshots**: The backend can snapshot and rollback system state when errors are detected
- **Health checks**: Both backend (`/health`) and frontend (`/api/health`) expose health endpoints for monitoring
