# ModelMesh Design Specification

**Created:** 2026-03-27
**Status:** Approved
**Project:** ModelMesh - Intelligent AI Gateway

---

## 1. Overview

### Vision

Create a unified API interface that intelligently routes development requests to the optimal AI model, balancing cost, performance, and capability.

### Goals

- **Primary:** Reduce AI operational costs by using local/free models for simple tasks, reserving expensive models for complex reasoning
- **Secondary:** Prevent vendor lock-in by abstracting the provider layer
- **MVP Scope:** Personal use (single user), no auth initially, architecture supports future expansion

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Core provider layer | LiteLLM | Battle-tested unified interface, saves months of adapter development |
| Architecture | Modular monolith | Simpler for MVP, can split to microservices later |
| API format | OpenAI-compatible + custom | Maximum compatibility with existing tools |
| Streaming | Required in MVP | Essential for coding/chat UX |
| Memory | Redis-backed sessions | Makes the system usable for real work |
| Deployment | Docker Compose | One-command startup, portable |
| Authentication | Simple API key | Single key for MVP, extensible to multi-user later |
| Secrets | Environment variables | Never store API keys in database |

---

## 2. Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ModelMesh Stack                             │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐  │
│  │ VS Code     │    │ Dashboard   │    │ Direct API Clients     │  │
│  │ Extension   │    │ (Next.js)   │    │ (curl, Postman, etc)   │  │
│  └──────┬──────┘    └──────┬──────┘    └───────────┬─────────────┘  │
│         │                  │                       │                 │
│         └──────────────────┼───────────────────────┘                 │
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                    FastAPI Gateway                              ││
│  │  • /v1/chat/completions (OpenAI-compatible)                    ││
│  │  • /v1/models, /v1/personas, /v1/conversations                 ││
│  │  • /api/internal/* (custom ModelMesh endpoints)                ││
│  └─────────────────────────┬───────────────────────────────────────┘│
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                    Core Services                                 ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  ││
│  │  │ Router       │  │ Memory       │  │ Cost Tracker         │  ││
│  │  │ (persona →   │  │ (Redis       │  │ (token counting,     │  ││
│  │  │  model)      │  │  sessions)   │  │  rate estimation)    │  ││
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘  ││
│  └─────────────────────────┬───────────────────────────────────────┘│
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                    LiteLLM Proxy                                 ││
│  │  Unified interface to: Ollama, Anthropic, Gemini, OpenAI        ││
│  └─────────────────────────┬───────────────────────────────────────┘│
│                            ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                    Providers (External)                          ││
│  │  • Ollama (local or glm-5:cloud)                                ││
│  │  • Anthropic (Claude)                                           ││
│  │  • Google (Gemini)                                              ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐                            │
│  │ PostgreSQL     │  │ Redis          │                            │
│  │ (persistent)   │  │ (cache/queue)  │                            │
│  └────────────────┘  └────────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

### Components

| Component | Technology | Purpose |
|-----------|-------------|---------|
| API Gateway | FastAPI | Request handling, routing, streaming |
| Provider Layer | LiteLLM | Unified interface to multiple AI providers |
| Memory Store | Redis | Conversation history, session context |
| Persistent Store | PostgreSQL | Providers, models, personas, logs |
| Dashboard | Next.js | Web UI for management and analytics |
| Extension | VS Code API | IDE integration for development workflow |

---

## 3. Data Model

### Schema

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Core configuration tables
CREATE TABLE providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,           -- 'ollama', 'anthropic', 'google'
    display_name VARCHAR(200),                    -- 'Ollama (Local)', 'Anthropic (Claude)'
    api_base_url VARCHAR(500),                    -- 'http://localhost:11434', null for SDK-based
    auth_type VARCHAR(50) DEFAULT 'none',         -- 'bearer', 'api_key', 'none'
    config JSONB DEFAULT '{}',                     -- provider-specific settings (NOT for API keys)
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id UUID REFERENCES providers(id) ON DELETE CASCADE,
    model_id VARCHAR(200) NOT NULL,               -- 'claude-sonnet-4-6', 'gemini-2.5-pro'
    display_name VARCHAR(200),                    -- 'Claude Sonnet 4.6'
    cost_per_1m_input DECIMAL(10,6) DEFAULT 0,    -- Cost per million input tokens
    cost_per_1m_output DECIMAL(10,6) DEFAULT 0,   -- Cost per million output tokens
    context_window INTEGER CHECK (context_window > 0),
    capabilities JSONB DEFAULT '{}',              -- {"vision": true, "streaming": true, "function_calling": true}
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(provider_id, model_id)
);

CREATE TABLE personas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,            -- 'Python Architect', 'Quick Helper'
    description TEXT,
    system_prompt TEXT,
    primary_model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    fallback_model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    routing_rules JSONB DEFAULT '{}',             -- {"max_cost": 0.05, "prefer_local": false, "timeout_seconds": 60}
    memory_enabled BOOLEAN DEFAULT true,
    max_memory_messages INTEGER DEFAULT 10 CHECK (max_memory_messages > 0),
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Operational tables
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id UUID REFERENCES personas(id) ON DELETE SET NULL,
    external_id VARCHAR(100) UNIQUE,               -- Client-provided conversation ID (optional)
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    model_used UUID REFERENCES models(id) ON DELETE SET NULL,
    tokens_in INTEGER CHECK (tokens_in >= 0),
    tokens_out INTEGER CHECK (tokens_out >= 0),
    latency_ms INTEGER CHECK (latency_ms >= 0),
    estimated_cost DECIMAL(10,6) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE request_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    persona_id UUID REFERENCES personas(id) ON DELETE SET NULL,
    model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    provider_id UUID REFERENCES providers(id) ON DELETE SET NULL,
    input_tokens INTEGER CHECK (input_tokens >= 0),
    output_tokens INTEGER CHECK (output_tokens >= 0),
    latency_ms INTEGER CHECK (latency_ms >= 0),
    estimated_cost DECIMAL(10,6) DEFAULT 0,
    success BOOLEAN,
    error_message TEXT,                           -- Sanitized error (no sensitive data)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at DESC);
CREATE INDEX idx_request_logs_created_at ON request_logs(created_at DESC);
CREATE INDEX idx_conversations_persona ON conversations(persona_id);
CREATE INDEX idx_personas_default ON personas(is_default) WHERE is_default = true;

-- Seed data for default providers
INSERT INTO providers (name, display_name, api_base_url, auth_type) VALUES
    ('ollama', 'Ollama (Local/Cloud)', 'http://localhost:11434', 'none'),
    ('anthropic', 'Anthropic', NULL, 'api_key'),
    ('google', 'Google AI', NULL, 'api_key');
```

### JSONB Schemas

**models.capabilities:**
```json
{
  "vision": true,
  "streaming": true,
  "function_calling": true,
  "context_window": 200000
}
```

**personas.routing_rules:**
```json
{
  "max_cost": 0.05,           // Maximum estimated cost per request
  "prefer_local": false,      // Prefer local models when available
  "timeout_seconds": 60,      // Request timeout override
  "max_tokens": 4096          // Default max tokens for responses
}
```

**providers.config:**
```json
{
  "timeout_seconds": 120,     // Provider-specific timeout
  "retry_count": 3,           // Number of retries on failure
  "rate_limit_rpm": 500       // Rate limit (requests per minute)
}
```

### Key Design Decisions

- No `users` table — single-user for MVP, easy to add later
- `personas` are the core abstraction — bundle model choice, system prompt, and routing rules
- `conversations` and `messages` support memory feature
- `request_logs` separate from messages for analytics
- JSONB columns for flexible extension without migrations
- API keys stored in environment variables — NEVER in database
- Indexes on `messages.conversation_id` and `request_logs.created_at` for query performance
- Check constraints on numeric fields to prevent invalid data
- `SET NULL` on foreign key deletions to preserve audit history

---

## 4. API Design

### OpenAI-Compatible Endpoints

```
POST   /v1/chat/completions     -- Main chat endpoint (streaming supported)
GET    /v1/models               -- List available models
GET    /v1/models/{model_id}    -- Get model details
```

#### Request Format

```json
{
  "model": "python-architect",      // Can be persona name OR model ID
  "messages": [
    {"role": "system", "content": "..."},  // Optional, overrides persona prompt
    {"role": "user", "content": "..."}
  ],
  "stream": true,
  "conversation_id": "uuid",        // Optional, for memory continuity
  "temperature": 0.7,
  "max_tokens": 4096
}
```

#### Response Format

```json
{
  "id": "chatcmpl-uuid",
  "object": "chat.completion",
  "model": "claude-sonnet-4-6",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "..."},
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 500,
    "total_tokens": 650
  },
  "modelmesh": {                     // Custom metadata
    "persona_used": "python-architect",
    "actual_model": "claude-sonnet-4-6",
    "estimated_cost": 0.0023,
    "provider": "anthropic"
  }
}
```

### ModelMesh Custom Endpoints

```
GET    /v1/personas                    -- List personas (paginated)
POST   /v1/personas                    -- Create persona
GET    /v1/personas/{id}               -- Get persona details
PATCH  /v1/personas/{id}               -- Update persona
DELETE /v1/personas/{id}               -- Delete persona

GET    /v1/conversations               -- List conversations (paginated)
POST   /v1/conversations               -- Create conversation
GET    /v1/conversations/{id}/messages  -- Get conversation history (paginated)
DELETE /v1/conversations/{id}           -- Delete conversation

GET    /v1/stats/costs                 -- Cost summary (?days=7&group_by=model)
GET    /v1/stats/usage                 -- Token usage breakdown (?days=7&group_by=provider)
```

### Pagination

All list endpoints support pagination:
```
GET /v1/personas?limit=20&offset=0
GET /v1/conversations?limit=50&offset=100
```

Response format:
```json
{
  "data": [...],
  "total": 150,
  "limit": 20,
  "offset": 0,
  "has_more": true
}
```

### Persona Create/Update

```json
// POST /v1/personas
{
  "name": "python-architect",
  "description": "Expert Python code reviewer and architect",
  "system_prompt": "You are an expert Python architect...",
  "primary_model_id": "uuid",
  "fallback_model_id": "uuid",
  "routing_rules": {
    "max_cost": 0.05,
    "prefer_local": false
  },
  "memory_enabled": true,
  "max_memory_messages": 10
}
```

### Error Responses

All errors follow this format:
```json
{
  "error": {
    "type": "invalid_request_error" | "authentication_error" | "model_error" | "rate_limit_error",
    "message": "Human-readable error message",
    "code": "ERROR_CODE",
    "details": {}
  }
}
```

Error codes:
- `persona_not_found` - Persona ID/name doesn't exist
- `model_unavailable` - Model is inactive or provider is down
- `all_models_failed` - All models in failover chain failed
- `cost_limit_exceeded` - Request exceeds max_cost routing rule
- `context_window_exceeded` - Messages exceed model context window
- `invalid_api_key` - Provider API key is invalid/expired

### Streaming Format

For `stream: true`, returns Server-Sent Events in OpenAI format:

```
data: {"id":"chatcmpl-uuid","choices":[{"delta":{"content":"Hello"},"index":0}]}
data: {"id":"chatcmpl-uuid","choices":[{"delta":{"content":" world"},"index":0}]}
data: [DONE]
```

---

## 5. Core Services

### Router Logic

```python
async def route_request(persona_id: str, messages: list, conversation_id: str = None):
    # 1. Resolve persona (by name or ID)
    persona = await get_persona(persona_id)
    if not persona:
        # Try to find by name, then raise if not found
        raise PersonaNotFoundError(persona_id)
    
    # 2. Build context with memory (if enabled and Redis available)
    if persona.memory_enabled and conversation_id:
        try:
            messages = await memory.get_context(conversation_id, messages, persona.max_memory_messages)
        except RedisUnavailableError:
            logger.warning("Redis unavailable, proceeding without conversation context")
            # Graceful degradation: continue without memory
    
    # 3. Resolve model (check if active)
    primary_model = await get_model(persona.primary_model_id)
    if not primary_model or not primary_model.is_active:
        primary_model = None
    
    fallback_model = None
    if persona.fallback_model_id:
        fallback_model = await get_model(persona.fallback_model_id)
        if not fallback_model or not fallback_model.is_active:
            fallback_model = None
    
    # 4. Check capability requirements (e.g., vision for images)
    required_capabilities = extract_required_capabilities(messages)
    if required_capabilities:
        if primary_model and not has_capabilities(primary_model, required_capabilities):
            primary_model = None
        if fallback_model and not has_capabilities(fallback_model, required_capabilities):
            fallback_model = None
    
    # 5. Check cost rules
    estimated_tokens = estimate_tokens(messages)
    estimated_cost = calculate_cost(estimated_tokens, primary_model)
    
    if persona.routing_rules.get("max_cost") and estimated_cost > persona.routing_rules["max_cost"]:
        if fallback_model:
            primary_model = fallback_model
            fallback_model = None
        else:
            raise CostLimitExceededError(estimated_cost, persona.routing_rules["max_cost"])
    
    # 6. Ensure we have at least one model
    if not primary_model:
        raise NoModelAvailableError(persona_id)
    
    # 7. Try primary model, failover if needed
    try:
        response = await call_model(primary_model, messages, stream=True)
        return response
    except (RateLimitError, TimeoutError, APIError) as e:
        log_error(e, primary_model)
        if fallback_model:
            try:
                response = await call_model(fallback_model, messages, stream=True)
                return response
            except Exception as fallback_error:
                log_error(fallback_error, fallback_model)
                raise AllModelsFailedError(primary_model, fallback_model, [e, fallback_error])
        raise AllModelsFailedError(primary_model, None, [e])
```

### Memory Manager

```python
class MemoryManager:
    def __init__(self, redis: Redis, config: Config):
        self.redis = redis
        self.default_ttl = config.memory_ttl_seconds  # Configurable, default 86400 (24h)
        self.enabled = True
    
    async def health_check(self) -> bool:
        """Check if Redis is available."""
        try:
            await self.redis.ping()
            self.enabled = True
            return True
        except Exception:
            self.enabled = False
            return False
    
    async def get_context(self, conversation_id: str, new_messages: list, max_messages: int):
        """Retrieve recent message history and append new messages."""
        if not self.enabled:
            raise RedisUnavailableError()
        
        key = f"conversation:{conversation_id}:messages"
        # Get last N messages (FIFO - oldest first)
        history = await self.redis.lrange(key, -max_messages, -1)
        history = [json.loads(m) for m in history]
        return history + new_messages
    
    async def store_messages(self, conversation_id: str, messages: list, max_messages: int = None):
        """Persist messages to conversation history with configurable limit."""
        if not self.enabled:
            return  # Graceful degradation: skip storing
        
        key = f"conversation:{conversation_id}:messages"
        for msg in messages:
            await self.redis.rpush(key, json.dumps(msg))
        
        # Enforce max_messages limit (trim old messages)
        limit = max_messages or 100  # Default to 100 if not specified
        await self.redis.ltrim(key, -limit, -1)
        
        # Set/configure TTL
        await self.redis.expire(key, self.default_ttl)
    
    async def clear_conversation(self, conversation_id: str):
        """Clear conversation memory."""
        if not self.enabled:
            return
        
        await self.redis.delete(f"conversation:{conversation_id}:messages")
    
    async def create_conversation_id(self) -> str:
        """Generate a new conversation ID if client doesn't provide one."""
        return str(uuid.uuid4())
```

### Cost Tracker

```python
class CostTracker:
    async def estimate_cost(self, messages: list, model: Model) -> Decimal:
        """Estimate cost before making request."""
        tokens = count_tokens(messages, model)
        input_cost = (tokens / 1_000_000) * model.cost_per_1m_input
        output_cost = (tokens * 2 / 1_000_000) * model.cost_per_1m_output
        return input_cost + output_cost
    
    async def log_request(self, request_log: RequestLog):
        """Log actual usage after request completes."""
        await self.db.insert("request_logs", request_log)
```

### LiteLLM Integration

```python
from litellm import acompletion  # Note: async version

async def call_model(model_id: str, messages: list, stream: bool = True, **params):
    """Call model via LiteLLM with unified interface."""
    model = await get_model(model_id)
    provider = await get_provider(model.provider_id)
    
    # LiteLLM format: "provider/model_name"
    litellm_model = f"{provider.name}/{model.model_id}"
    
    # Get API key from environment (never from database)
    api_key = os.environ.get(f"{provider.name.upper()}_API_KEY")
    
    # Use acompletion for async support
    response = await acompletion(
        model=litellm_model,
        messages=messages,
        stream=stream,
        api_base=provider.api_base_url,
        api_key=api_key,
        **params
    )
    
    return response
```

### Error Handling

```python
class ModelMeshError(Exception):
    """Base error for all ModelMesh errors."""
    def __init__(self, message: str, code: str, details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

class PersonaNotFoundError(ModelMeshError):
    def __init__(self, persona_id: str):
        super().__init__(
            f"Persona not found: {persona_id}",
            "persona_not_found",
            {"persona_id": persona_id}
        )

class AllModelsFailedError(ModelMeshError):
    def __init__(self, primary, fallback, errors):
        super().__init__(
            "All models in failover chain failed",
            "all_models_failed",
            {"primary": primary, "fallback": fallback, "errors": [str(e) for e in errors]}
        )

class CostLimitExceededError(ModelMeshError):
    def __init__(self, estimated: float, limit: float):
        super().__init__(
            f"Estimated cost ${estimated:.4f} exceeds limit ${limit:.4f}",
            "cost_limit_exceeded",
            {"estimated_cost": estimated, "max_cost": limit}
        )
```

---

## 6. VS Code Extension (MVP)

### Features

1. Send selection to ModelMesh (right-click or keyboard shortcut)
2. Persona picker (dropdown to select active persona)
3. Response panel (side panel with streaming output)
4. Conversation continuity (responses are part of a session)

### Project Structure

```
modelmesh-vscode/
├── src/
│   ├── extension.ts          -- Entry point, command registration
│   ├── api/
│   │   └── client.ts         -- ModelMesh API client
│   ├── providers/
│   │   ├── personaProvider.ts -- Tree view for persona selection
│   │   └── responseProvider.ts -- Output channel for responses
│   ├── commands/
│   │   ├── sendSelection.ts   -- Send highlighted text to API
│   │   └── newConversation.ts -- Clear context, start fresh
│   └── utils/
│       └── config.ts          -- Extension settings
├── package.json              -- Extension manifest
└── README.md
```

### Commands

```json
"commands": [
  { "command": "modelmesh.sendSelection", "title": "ModelMesh: Ask Selected Text" },
  { "command": "modelmesh.newConversation", "title": "ModelMesh: New Conversation" },
  { "command": "modelmesh.selectPersona", "title": "ModelMesh: Select Persona" }
]
```

### Settings

```json
{
  "modelmesh.apiUrl": "http://localhost:18800/v1",
  "modelmesh.defaultPersona": "quick-helper",
  "modelmesh.streamResponses": true,
  "modelmesh.showCostInResponse": true
}
```

---

## 7. Project Structure

### Repository Layout

```
modelmesh/
├── docker-compose.yml        -- All services orchestrated
├── .env.example               -- Environment template
├── README.md
│
├── backend/                   -- FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/
│   │   ├── versions/
│   │   └── env.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── redis.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── routes/
│   └── tests/
│
├── frontend/                  -- Next.js dashboard
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│
├── extension/                 -- VS Code extension
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│
└── docs/
    ├── api.md
    ├── deployment.md
    └── personas.md
```

---

## 8. Development Phases

### Phase 1: Core API (Week 1)
- Docker Compose setup (FastAPI, Postgres, Redis)
- Alembic migrations for schema
- SQLAlchemy models
- Basic `/v1/chat/completions` endpoint
- LiteLLM integration for single provider (Ollama)
- Health check endpoints

### Phase 2: Multi-Provider (Week 2)
- Add Anthropic and Gemini providers
- Router logic with persona resolution
- Streaming response support
- Cost estimation and logging
- Error handling with failover

### Phase 3: Memory & Personas (Week 3)
- Redis-backed conversation memory
- Persona CRUD endpoints
- Persona-to-model routing
- Request logging to Postgres

### Phase 4: Dashboard (Week 4)
- Next.js frontend setup
- Conversation view
- Persona management UI
- Cost/usage stats display
- Model selection dropdown

### Phase 5: Extension (Week 5)
- VS Code extension scaffold
- Send selection to API
- Persona picker
- Response panel with streaming
- Insert/Copy functionality

### Phase 6: Polish & Deploy (Week 6)
- Integration tests
- Documentation
- Deployment configs
- Seed data scripts (default personas)

---

## 9. Authentication & Security

### MVP Authentication

Simple API key authentication for MVP:

```python
# Middleware
API_KEY = os.environ.get("MODELMESH_API_KEY")

async def verify_api_key(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid Authorization header")
    
    provided_key = auth_header[7:]  # Strip "Bearer "
    if provided_key != API_KEY:
        raise AuthenticationError("Invalid API key")
```

### Secrets Management

**Never store API keys in the database.** All provider credentials come from environment variables:

```bash
# .env (never committed to git)
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
MODELMESH_API_KEY=modelmesh-local-dev-key

# Docker Compose
services:
  backend:
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - MODELMESH_API_KEY=${MODELMESH_API_KEY}
```

### Security Checklist

- [ ] API keys loaded from environment variables only
- [ ] `.env` file in `.gitignore`
- [ ] Redis password configured in production (`REDIS_PASSWORD`)
- [ ] Error messages sanitized (no sensitive data leaked)
- [ ] Input validation on all endpoints (Pydantic schemas)
- [ ] Parameterized queries (SQLAlchemy ORM prevents SQL injection)
- [ ] TLS/HTTPS for production deployment (not required for localhost dev)

---

## 10. Docker Compose

```yaml
services:
  postgres:
    image: postgres:16
    volumes: [postgres_data:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: modelmesh
      POSTGRES_USER: modelmesh
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-modelmesh_local_dev}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U modelmesh -d modelmesh"]
      interval: 5s
      timeout: 5s
      retries: 5
    
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD:-modelmesh_redis_dev}
    volumes: [redis_data:/data]
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-modelmesh_redis_dev}", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    
  backend:
    build: ./backend
    ports: ["18800:18800"]
    depends_on: 
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
    environment:
      DATABASE_URL: postgresql://modelmesh:${POSTGRES_PASSWORD:-modelmesh_local_dev}@postgres/modelmesh
      REDIS_URL: redis://:${REDIS_PASSWORD:-modelmesh_redis_dev}@redis:6379
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      GOOGLE_API_KEY: ${GOOGLE_API_KEY}
      MODELMESH_API_KEY: ${MODELMESH_API_KEY:-modelmesh_local_dev}
    
  frontend:
    build: ./frontend
    ports: ["18801:3000"]
    depends_on: [backend]

volumes:
  postgres_data:
  redis_data:
```

---

## 11. Configuration

```yaml
# Environment variables
providers:
  ollama:
    base_url: ${OLLAMA_BASE_URL:-http://localhost:11434}
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}  # Required
  google:
    api_key: ${GOOGLE_API_KEY}     # Required

defaults:
  persona: quick-helper
  max_memory_messages: 10
  memory_ttl_seconds: 86400        # 24 hours (configurable)
  request_timeout_seconds: 60
```

---

## 12. Future Enhancements (Post-MVP)

- **User authentication** — Multi-user support with API keys
- **Auto-classifier** — Route requests automatically based on content type
- **Billing integration** — Stripe for cost tracking
- **Agent chains** — Sequential model processing
- **IDE plugins** — JetBrains, other editors
- **Advanced analytics** — Cost trends, model performance comparison

---

## 13. Out of Scope for MVP

- Multi-tenant isolation
- Billing/payment integration
- Auto-classification of request types
- User authentication (API keys)
- External Postgres support (Docker only for now)
- Remote Ollama configuration UI (config-file only)