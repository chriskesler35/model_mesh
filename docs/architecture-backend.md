# Backend Architecture

Python FastAPI backend for DevForgeAI.

## Stack

- Python 3.11+
- FastAPI
- SQLAlchemy async
- Alembic (migrations)
- LiteLLM (multi-provider LLM abstraction)
- Redis (optional, for rate limiting)
- SQLite (dev) / PostgreSQL (prod)

## Architecture Pattern

Service-oriented API with middleware pipeline.

## Entry Point

`app/main.py` creates the FastAPI app with a lifespan handler that runs:
- Table creation
- Migrations
- Auto-cleanup
- Seeding
- Model sync
- Telegram polling

## Layer Structure

### Routes

33 route groups providing an OpenAI-compatible chat API and application-specific endpoints.

### Schemas

Pydantic v2 request/response validation models.

### Services

| Service | Description |
|---------|-------------|
| **Router** | Routes chat through persona -> primary model -> fallback, with heuristic/LLM classification, cost limits, memory injection |
| **PersonaResolver** | Resolves persona configuration for chat routing |
| **ModelClient** | Wraps LiteLLM with provider-specific routing (Anthropic, Google, OpenRouter, Ollama, OpenAI, Codex OAuth, GitHub Copilot) |
| **MemoryManager** | Manages persistent memory storage and retrieval |
| **MemoryContext** | Provides memory context injection into conversations |
| **ContextSnapshot** | Captures and restores conversation context state |
| **IdentityContext** | Manages identity and persona context for sessions |
| **ProviderCredentials** | Handles API key and credential management for LLM providers |
| **CommandClassifier** | 3-tier safety classification (auto/notice/approval) + blocked for sandbox |
| **CommandExecutor** | Runs commands with recording, parses `CMD:` blocks from LLM output, GitHub auth via GIT_ASKPASS |
| **SandboxGuard** | Enforces sandbox restrictions on command execution |
| **SelfHealing** | Health checks, snapshots, recovery, rollback |
| **PhaseTemplates** | Template management for multi-agent pipeline phases |
| **CodexOAuth** | OAuth integration for Codex provider |
| **GithubCopilot** | GitHub Copilot provider integration |
| **AppSettingsHelper** | Application settings management |

### Models

18 SQLAlchemy models defining the database schema.

### Middleware

- **Auth**: API key + JWT authentication
- **Rate Limiter**: Redis-backed request rate limiting

## Authentication

- **Master API key** OR **JWT** (HS256, 7-day expiry)
- GitHub OAuth support
- Bcrypt password hashing

## Configuration

Pydantic `BaseSettings` loading from `.env` file.

## CORS

Open configuration: `allow_origins=["*"]`
