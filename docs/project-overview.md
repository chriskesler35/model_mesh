# Project Overview

## Project Name

**DevForgeAI** (also known as ModelMesh)

## Purpose

DevForgeAI is an intelligent AI development platform that provides a unified gateway for multiple AI model providers, with persona-based routing, development workflow orchestration, and IDE integration. It serves as a local-first AI command center for developers who want to work with multiple LLM providers through a single, consistent interface while maintaining full control over model selection, cost, and privacy.

## Repository Type

Multi-part monorepo with three distinct components that share a common data layer and communicate over REST and SSE.

---

## Tech Stack Summary

| Part      | Language       | Framework    | Database          | Key Dependencies                                       |
|-----------|----------------|--------------|-------------------|--------------------------------------------------------|
| Backend   | Python 3.11+   | FastAPI      | SQLite/PostgreSQL | SQLAlchemy, LiteLLM, Alembic, Redis, bcrypt, PyJWT     |
| Frontend  | TypeScript     | Next.js 14   | --                | React 18, Tailwind CSS                                  |
| Extension | TypeScript     | VS Code API  | --                | (no runtime dependencies)                               |

---

## Architecture

- **Backend**: Service-oriented Python backend exposing an OpenAI-compatible API (`/v1/chat/completions`, `/v1/models`, etc.). Uses SQLAlchemy ORM with async sessions, LiteLLM for multi-provider abstraction, and SSE for real-time streaming. Supports both SQLite (local) and PostgreSQL (Docker) databases.

- **Frontend**: Next.js 14 App Router application with server and client components. Tailwind CSS for styling. Communicates with the backend via REST calls and SSE streams. Includes a full chat interface, workbench, pipeline viewer, project manager, and admin settings.

- **Extension**: VS Code extension providing IDE-integrated chat and persona selection. Registers commands for sending code selections to the backend and displays personas in a sidebar TreeView.

---

## Key Features

### AI Gateway
- Multi-provider AI gateway supporting Ollama, Anthropic, Google, OpenRouter, OpenAI, and GitHub Copilot
- Persona-based model routing with configurable fallback chains
- OpenAI-compatible API for drop-in replacement with existing tools

### Chat and Interaction
- Full chat interface with streaming, markdown rendering, and syntax highlighting
- Inline image generation within conversations
- Conversation history with search and management

### Development Workflows
- Single-agent workbench with tool use (file operations, command execution, web search)
- Multi-agent pipelines supporting BMAD, GSD, and SuperPowers methodologies
- Approval gates between pipeline phases for human-in-the-loop control
- Per-phase model overrides and retry on failure

### Project Management
- Project creation with file browsing and editing
- Sandbox environments with venv, git integration, and environment variable management
- Context snapshots for project state capture

### Image Generation
- Gemini Imagen API integration (cloud)
- ComfyUI local integration with 6 workflow templates
- Task-based async generation with polling

### AI Identity System
- Configurable AI personality via `soul.md`
- User context via `user.md`
- Runtime identity via `identity.md`
- Preference learning from conversation patterns

### Collaboration
- Multi-user authentication with JWT tokens
- Workspace and session scoping
- Handoff support between users
- Public share links for conversations and artifacts

### Operations
- Remote access via Telegram bot and Tailscale
- Self-healing system with snapshots and rollback
- Hardware monitoring (GPU VRAM tracking, model fitness checks)
- Cost tracking and usage analytics per user, model, and provider

### Development Method Integration
- BMAD (Business, Management, Architecture, Development) methodology pipelines
- GSD (Get Stuff Done) workflow automation
- SuperPowers structured development flows
- GTrack progress tracking

---

## Supported AI Providers

| Provider        | Type   | Cost  | Notes                                        |
|-----------------|--------|-------|----------------------------------------------|
| Ollama          | Local  | Free  | Self-hosted open-source models               |
| Anthropic       | Cloud  | Paid  | Claude models (Haiku, Sonnet, Opus)          |
| Google          | Cloud  | Paid  | Gemini models + Imagen for image generation  |
| OpenRouter      | Cloud  | Paid  | Aggregator for 100+ models from many vendors |
| OpenAI          | Cloud  | Paid  | GPT-4, GPT-3.5, DALL-E                       |
| GitHub Copilot  | Cloud  | Paid  | Via Copilot token extraction                 |
| Codex OAuth     | Cloud  | Paid  | Via OAuth proxy integration                  |

---

## Getting Started

The project includes cross-platform setup tools:

- `install.py` -- automated installer for all dependencies
- `devforgeai.py` -- CLI runner (`start`, `stop`, `status` commands)
- `start.bat` / `Start-DevForgeAI.ps1` -- Windows launchers
- `docker-compose.yml` -- containerized deployment with PostgreSQL and Redis
- `ecosystem.config.js` -- PM2 process manager configuration for production
