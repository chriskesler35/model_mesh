# DevForgeAI Backend API Reference

> **Framework:** Python / FastAPI  
> **Base URL:** `http://localhost:8000` (default)  
> **Authentication:** API key via `X-API-Key` header unless noted otherwise  
> **Content-Type:** `application/json` (all request/response bodies)

---

## Table of Contents

1. [Health](#1-health)
2. [Chat Completions](#2-chat-completions)
3. [Conversations](#3-conversations)
4. [Models](#4-models)
5. [Model Sync](#5-model-sync)
6. [Model Validate](#6-model-validate)
7. [Model Lookup](#7-model-lookup)
8. [Personas](#8-personas)
9. [Providers](#9-providers)
10. [Stats](#10-stats)
11. [User Profile](#11-user-profile)
12. [Agents](#12-agents)
13. [Images](#13-images)
14. [Tasks](#14-tasks)
15. [System](#15-system)
16. [Remote](#16-remote)
17. [Telegram](#17-telegram)
18. [Identity](#18-identity)
19. [Workbench Sessions](#19-workbench-sessions)
20. [Pipelines](#20-pipelines)
21. [Projects](#21-projects)
22. [Runner](#22-runner)
23. [Methods](#23-methods)
24. [Sandbox](#24-sandbox)
25. [Collaboration](#25-collaboration)
26. [Auth](#26-auth)
27. [GitHub OAuth](#27-github-oauth)
28. [Shares](#28-shares)
29. [Hardware](#29-hardware)
30. [API Keys](#30-api-keys)
31. [Context](#31-context)
32. [Preferences](#32-preferences)
33. [App Settings](#33-app-settings)
34. [Workflows & ComfyUI](#34-workflows--comfyui)

---

## 1. Health

Top-level health check for load balancers and uptime monitors.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Returns server health status |

---

## 2. Chat Completions

OpenAI-compatible chat completions endpoint. Supports both streaming and non-streaming responses.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/chat/completions` | API Key + Rate Limit | Generate a chat completion |

**Request body parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `messages` | `array` | Yes | Array of message objects (`role`, `content`) |
| `model` | `string` | No | Persona name or ID to route the request |
| `model_override` | `string` | No | Override the underlying LLM model directly |
| `stream` | `boolean` | No | `true` for SSE streaming, `false` for single JSON response |
| `conversation_id` | `string` | No | Continue an existing conversation |
| `temperature` | `float` | No | Sampling temperature (0.0 - 2.0) |
| `max_tokens` | `integer` | No | Maximum tokens in the completion |

---

## 3. Conversations

Manage conversations and their messages.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/conversations` | API Key | List all conversations |
| `POST` | `/v1/conversations` | API Key | Create a new conversation |
| `GET` | `/v1/conversations/{id}` | API Key | Get a conversation by ID |
| `PATCH` | `/v1/conversations/{id}` | API Key | Update conversation metadata (title, etc.) |
| `DELETE` | `/v1/conversations/{id}` | API Key | Delete a conversation |
| `GET` | `/v1/conversations/{id}/messages` | API Key | List messages in a conversation |
| `POST` | `/v1/conversations/{id}/messages` | API Key | Add a message to a conversation |
| `PATCH` | `/v1/conversations/messages/{message_id}/image` | API Key | Update/attach an image to a message |
| `GET` | `/v1/conversations/cleanup` | API Key | Clean up orphaned or empty conversations |

---

## 4. Models

CRUD operations for LLM model definitions.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/models` | API Key | List all models |
| `POST` | `/v1/models` | API Key | Create a new model definition |
| `GET` | `/v1/models/{id}` | API Key | Get a model by ID |
| `PATCH` | `/v1/models/{id}` | API Key | Update a model definition |
| `DELETE` | `/v1/models/{id}` | API Key | Delete a model definition |
| `GET` | `/v1/models/provider/{name}` | API Key | List models filtered by provider name |

---

## 5. Model Sync

Synchronize model catalogs from upstream providers (OpenRouter, OpenAI, etc.).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/models/sync` | API Key | Trigger a model sync from provider APIs |
| `GET` | `/v1/models/sync/status` | API Key | Check the status of an in-progress sync |

---

## 6. Model Validate

Validate that a model configuration is functional.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/models/validate` | API Key | Validate a model by sending a test request |

---

## 7. Model Lookup

Public endpoints for model discovery and suggestions.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/model-lookup/lookup` | None | Look up model details by name or identifier |
| `GET` | `/v1/model-lookup/suggestions/{provider}` | None | Get suggested models for a given provider |

---

## 8. Personas

CRUD operations for AI personas. Personas can be retrieved by UUID or by name.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/personas` | API Key | List all personas |
| `POST` | `/v1/personas` | API Key | Create a new persona |
| `GET` | `/v1/personas/{id_or_name}` | API Key | Get a persona by UUID or name |
| `PATCH` | `/v1/personas/{id}` | API Key | Update a persona |
| `DELETE` | `/v1/personas/{id}` | API Key | Delete a persona |

---

## 9. Providers

Read-only listing of configured LLM providers.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/providers` | API Key | List all available providers and their status |

---

## 10. Stats

Usage and cost analytics.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/stats/costs` | API Key | Get cost breakdown by model/provider/time period |
| `GET` | `/v1/stats/usage` | API Key | Get token usage statistics |

---

## 11. User Profile

User profile, memory, and modification history.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/user` | API Key | Get current user profile |
| `PATCH` | `/v1/user` | API Key | Update user profile fields |
| `GET` | `/v1/memory` | API Key | List user memory entries |
| `POST` | `/v1/memory` | API Key | Create a memory entry |
| `PATCH` | `/v1/memory/{id}` | API Key | Update a memory entry |
| `DELETE` | `/v1/memory/{id}` | API Key | Delete a memory entry |
| `GET` | `/v1/modifications` | API Key | List modification history |

---

## 12. Agents

Agent configuration for multi-agent pipelines (BMAD/GSD/SuperPowers).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/agents` | API Key | List all agents |
| `POST` | `/v1/agents` | API Key | Create a new agent |
| `GET` | `/v1/agents/{id}` | API Key | Get an agent by ID |
| `PATCH` | `/v1/agents/{id}` | API Key | Update an agent |
| `DELETE` | `/v1/agents/{id}` | API Key | Delete an agent |
| `GET` | `/v1/agents/method-phases` | API Key | List available method phases for agent assignment |
| `GET` | `/v1/agents/defaults` | API Key | Get default agent configurations |

---

## 13. Images

Image generation and retrieval. Supports AI-generated images via configured providers.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/images/generate` | API Key | Generate an image from a text prompt |
| `GET` | `/v1/images` | API Key | List generated images |
| `GET` | `/v1/images/{id}` | API Key | Get image metadata by ID |
| `GET` | `/v1/img/{id}` | None (public) | Serve the raw image file by ID |

---

## 14. Tasks

Background task management and notification system.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/tasks` | API Key | Create a new background task |
| `GET` | `/v1/tasks` | API Key | List all tasks |
| `GET` | `/v1/tasks/{id}` | API Key | Get task details by ID |
| `GET` | `/v1/tasks/notifications` | API Key | Get pending task notifications |
| `POST` | `/v1/tasks/{id}/acknowledge` | API Key | Acknowledge a task notification |

---

## 15. System

System administration, health monitoring, snapshots, and process management.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/system/health` | API Key | Detailed system health with component status |
| `POST` | `/v1/system/snapshots` | API Key | Create a system snapshot |
| `GET` | `/v1/system/snapshots` | API Key | List available snapshots |
| `POST` | `/v1/system/recover` | API Key | Recover system from a snapshot |
| `POST` | `/v1/system/rollback` | API Key | Rollback to a previous system state |
| `GET` | `/v1/system/processes` | API Key | List running system processes |
| `GET` | `/v1/system/logs` | API Key | Retrieve system logs |
| `POST` | `/v1/system/processes/{id}/start` | API Key | Start a system process |
| `POST` | `/v1/system/processes/{id}/stop` | API Key | Stop a system process |
| `POST` | `/v1/system/processes/{id}/restart` | API Key | Restart a system process |
| `GET` | `/v1/system/info` | API Key | Get system information (version, uptime, etc.) |
| `POST` | `/v1/system/restart` | API Key | Restart the backend server |

---

## 16. Remote

Remote access and Tailscale-based session management.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/remote/health` | None | Remote health check endpoint |
| `GET` | `/v1/remote/sessions` | None | List active remote sessions |
| `POST` | `/v1/remote/sessions` | None | Create a new remote session |
| `GET` | `/v1/remote/sessions/{id}` | None | Get remote session details |
| `DELETE` | `/v1/remote/sessions/{id}` | None | Terminate a remote session |
| `GET` | `/v1/remote/tailscale-info` | API Key | Get Tailscale network information |

---

## 17. Telegram

Telegram bot integration for mobile notifications and interaction.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/telegram/webhook` | None | Receive incoming Telegram webhook events |
| `POST` | `/v1/telegram/send` | None | Send a message via Telegram bot |
| `GET` | `/v1/telegram/status` | None | Get Telegram bot connection status |
| `POST` | `/v1/telegram/register-webhook` | None | Register the webhook URL with Telegram |
| `DELETE` | `/v1/telegram/webhook` | None | Unregister the Telegram webhook |
| `GET` | `/v1/telegram/webhook-info` | None | Get current webhook registration info |

---

## 18. Identity

AI identity and soul configuration.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/identity/status` | API Key | Get identity system status |
| `GET` | `/v1/identity/soul` | API Key | Get the AI soul/personality configuration |
| `PUT` | `/v1/identity/soul` | API Key | Update the AI soul/personality configuration |
| `GET` | `/v1/identity/user` | API Key | Get identity user profile |
| `PUT` | `/v1/identity/user` | API Key | Update identity user profile |
| `GET` | `/v1/identity/identity-file` | API Key | Get the raw identity file |
| `PUT` | `/v1/identity/identity-file` | API Key | Update the raw identity file |
| `POST` | `/v1/identity/setup` | API Key | Run initial identity setup wizard |

---

## 19. Workbench Sessions

Interactive workbench sessions for AI-assisted development with streaming output.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/workbench/sessions` | API Key | List all workbench sessions |
| `POST` | `/v1/workbench/sessions` | API Key | Create a new workbench session |
| `GET` | `/v1/workbench/sessions/{id}` | API Key | Get session details |
| `PATCH` | `/v1/workbench/sessions/{id}` | API Key | Update session metadata |
| `DELETE` | `/v1/workbench/sessions/{id}` | API Key | Delete a session |
| `POST` | `/v1/workbench/sessions/{id}/message` | API Key | Send a message to the session |
| `GET` | `/v1/workbench/sessions/{id}/stream` | None (SSE) | Stream session events via Server-Sent Events |
| `POST` | `/v1/workbench/sessions/{id}/cancel` | API Key | Cancel the current session operation |
| `POST` | `/v1/workbench/sessions/{id}/bypass` | API Key | Bypass a pending approval gate |
| `POST` | `/v1/workbench/sessions/{id}/approve` | API Key | Approve a pending command |
| `POST` | `/v1/workbench/sessions/{id}/reject` | API Key | Reject a pending command |

---

## 20. Pipelines

Multi-agent pipeline orchestration with approval gates and streaming status.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/workbench/pipelines` | API Key | Create and start a new pipeline |
| `GET` | `/v1/workbench/pipelines/{id}` | API Key | Get pipeline status and phase details |
| `GET` | `/v1/workbench/pipelines/{id}/stream` | None (SSE) | Stream pipeline events via Server-Sent Events |
| `POST` | `/v1/workbench/pipelines/{id}/approve` | API Key | Approve a pipeline approval gate |
| `POST` | `/v1/workbench/pipelines/{id}/reject` | API Key | Reject a pipeline approval gate |
| `POST` | `/v1/workbench/pipelines/{id}/skip` | API Key | Skip the current pipeline phase |
| `POST` | `/v1/workbench/pipelines/{id}/cancel` | API Key | Cancel a running pipeline |

---

## 21. Projects

Project management with templates, file browsing, and sandbox environments.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/projects` | API Key | List all projects |
| `POST` | `/v1/projects` | API Key | Create a new project |
| `GET` | `/v1/projects/{id}` | API Key | Get project details |
| `PATCH` | `/v1/projects/{id}` | API Key | Update project metadata |
| `DELETE` | `/v1/projects/{id}` | API Key | Delete a project |
| `GET` | `/v1/projects/templates` | API Key | List available project templates |
| `GET` | `/v1/projects/{id}/files` | API Key | List files in the project directory |
| `GET` | `/v1/projects/{id}/files/read` | API Key | Read a specific file from the project |
| `GET` | `/v1/projects/{id}/sandbox` | API Key | Get project sandbox status |
| `POST` | `/v1/projects/{id}/sandbox` | API Key | Initialize or configure the project sandbox |

---

## 22. Runner

Code execution runner with streaming output.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/runner/config` | API Key | Get runner configuration |
| `PUT` | `/v1/runner/config` | API Key | Update runner configuration |
| `GET` | `/v1/runner/status` | API Key | Get runner execution status |
| `POST` | `/v1/runner/run` | API Key | Execute code or a command |
| `POST` | `/v1/runner/stop` | API Key | Stop a running execution |
| `GET` | `/v1/runner/stream` | None (SSE) | Stream execution output via Server-Sent Events |
| `DELETE` | `/v1/runner/buffer` | API Key | Clear the runner output buffer |

---

## 23. Methods

Development methodology management (e.g., TDD, BDD, Agile workflows).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/methods` | API Key | List all available methods |
| `GET` | `/v1/methods/active` | API Key | Get the currently active method |
| `POST` | `/v1/methods/active` | API Key | Set the active method |
| `GET` | `/v1/methods/active/prompt` | API Key | Get the active method's system prompt |
| `POST` | `/v1/methods/activate` | API Key | Activate a specific method |
| `POST` | `/v1/methods/stack` | API Key | Set the full method stack |
| `POST` | `/v1/methods/stack-add` | API Key | Push a method onto the stack |
| `POST` | `/v1/methods/stack-remove` | API Key | Remove a method from the stack |
| `DELETE` | `/v1/methods/stack` | API Key | Clear the method stack |
| `GET` | `/v1/methods/{id}` | API Key | Get a method by ID |

---

## 24. Sandbox

Isolated development environment management.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/sandbox/status` | API Key | Get sandbox environment status |
| `POST` | `/v1/sandbox/venv` | API Key | Create a Python virtual environment |
| `DELETE` | `/v1/sandbox/venv` | API Key | Remove the virtual environment |
| `POST` | `/v1/sandbox/install` | API Key | Install packages into the sandbox |
| `POST` | `/v1/sandbox/git/init` | API Key | Initialize a git repository in the sandbox |
| `POST` | `/v1/sandbox/snapshot` | API Key | Create a sandbox snapshot |
| `POST` | `/v1/sandbox/rollback` | API Key | Rollback sandbox to a previous snapshot |
| `GET` | `/v1/sandbox/env-vars` | API Key | List sandbox environment variables |
| `POST` | `/v1/sandbox/env-vars` | API Key | Set sandbox environment variables |

---

## 25. Collaboration

Multi-user collaboration, audit trails, handoffs, and workspaces.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/collaboration/users` | API Key | List collaborator users |
| `POST` | `/v1/collaboration/users` | API Key | Add a collaborator user |
| `PATCH` | `/v1/collaboration/users/{id}` | API Key | Update a collaborator |
| `DELETE` | `/v1/collaboration/users/{id}` | API Key | Remove a collaborator |
| `POST` | `/v1/collaboration/audit` | API Key | Create an audit log entry |
| `GET` | `/v1/collaboration/audit` | API Key | List audit log entries |
| `POST` | `/v1/collaboration/handoff` | API Key | Create a handoff request |
| `GET` | `/v1/collaboration/handoff` | API Key | List handoff requests |
| `POST` | `/v1/collaboration/handoff/{id}/accept` | API Key | Accept a handoff request |
| `GET` | `/v1/collaboration/workspaces` | API Key | List workspaces |
| `POST` | `/v1/collaboration/workspaces` | API Key | Create a workspace |
| `PATCH` | `/v1/collaboration/workspaces/{id}` | API Key | Update a workspace |
| `DELETE` | `/v1/collaboration/workspaces/{id}` | API Key | Delete a workspace |

---

## 26. Auth

Authentication endpoints for multi-user access.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/auth/login` | None | Authenticate and receive a bearer token |
| `GET` | `/v1/auth/me` | Bearer Token | Get the authenticated user's profile |
| `POST` | `/v1/auth/logout` | Bearer Token | Invalidate the current session |

---

## 27. GitHub OAuth

GitHub OAuth flow for repository integration.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/github/oauth/status` | None | Check GitHub OAuth connection status |
| `GET` | `/v1/github/oauth/authorize` | None | Initiate the GitHub OAuth authorization flow |
| `POST` | `/v1/github/oauth/callback` | None | Handle the GitHub OAuth callback |

---

## 28. Shares

Public share links for conversations and artifacts.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/shares` | API Key | Create a new share link |
| `GET` | `/v1/shares` | API Key | List all share links |
| `DELETE` | `/v1/shares/{id}` | API Key | Revoke a share link |
| `GET` | `/v1/share/{token}` | None (public) | Access shared content by token |

---

## 29. Hardware

Hardware capability detection and model compatibility checks.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/hardware/status` | API Key | Get hardware status (GPU, VRAM, CPU, RAM) |
| `GET` | `/v1/hardware/check/{model_id}` | API Key | Check if hardware can run a specific model |

---

## 30. API Keys

Manage provider API keys stored in the backend.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/api-keys` | API Key | List all configured provider API keys (masked) |
| `PUT` | `/v1/api-keys/{provider}` | API Key | Set or update an API key for a provider |
| `GET` | `/v1/api-keys/{provider}/clear-impact` | API Key | Preview the impact of clearing a provider key |
| `DELETE` | `/v1/api-keys/{provider}` | API Key | Delete the API key for a provider |

---

## 31. Context

Conversation context recovery and memory management.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/context/recover/{conversation_id}` | API Key | Recover context for a conversation |
| `GET` | `/v1/context/snapshots` | API Key | List context snapshots |
| `GET` | `/v1/context/memory` | API Key | Get context memory state |
| `PUT` | `/v1/context/memory` | API Key | Update context memory |

---

## 32. Preferences

User preferences with automatic detection support.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/preferences` | API Key | Get all user preferences |
| `POST` | `/v1/preferences` | API Key | Create or set preferences |
| `PATCH` | `/v1/preferences` | API Key | Update specific preferences |
| `DELETE` | `/v1/preferences` | API Key | Reset preferences to defaults |
| `POST` | `/v1/preferences/detect` | API Key | Auto-detect preferences (timezone, locale, etc.) |

---

## 33. App Settings

Application-level settings (distinct from user preferences).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/settings/app` | API Key | Get all application settings |
| `GET` | `/v1/settings/app/{key}` | API Key | Get a specific setting by key |
| `PUT` | `/v1/settings/app` | API Key | Update application settings |

---

## 34. Workflows & ComfyUI

Workflow templates and ComfyUI integration for image generation pipelines.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/workflows` | API Key | List all available workflows |
| `GET` | `/v1/workflows/{id}` | API Key | Get workflow details by ID |
| `GET` | `/v1/comfyui/checkpoints` | API Key | List available ComfyUI checkpoints |
| `GET` | `/v1/comfyui/loras` | API Key | List available ComfyUI LoRAs |
| `GET` | `/v1/comfyui/status` | API Key | Get ComfyUI server connection status |

---

## Authentication Notes

- **API Key:** Most endpoints require an `X-API-Key` header. The key is configured in the backend environment.
- **Bearer Token:** The `/v1/auth/me` and `/v1/auth/logout` endpoints use standard `Authorization: Bearer <token>` headers after login.
- **Rate Limiting:** The chat completions endpoint enforces rate limits per API key.
- **Public Endpoints:** Endpoints marked "None" for auth are accessible without credentials. These include health checks, SSE streams, public image serving, share access, model lookup, and Telegram webhooks.

## SSE Streaming Endpoints

Several endpoints use Server-Sent Events (SSE) for real-time streaming:

| Endpoint | Purpose |
|----------|---------|
| `/v1/workbench/sessions/{id}/stream` | Workbench session output |
| `/v1/workbench/pipelines/{id}/stream` | Pipeline phase progress |
| `/v1/runner/stream` | Code execution output |

SSE streams do not require authentication and use `text/event-stream` content type. Connect with `EventSource` or equivalent SSE client.

## Common Response Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `204` | No content (successful delete) |
| `400` | Bad request / validation error |
| `401` | Unauthorized (missing or invalid auth) |
| `403` | Forbidden (insufficient permissions) |
| `404` | Resource not found |
| `409` | Conflict (duplicate resource) |
| `422` | Unprocessable entity (FastAPI validation) |
| `429` | Rate limit exceeded |
| `500` | Internal server error |
