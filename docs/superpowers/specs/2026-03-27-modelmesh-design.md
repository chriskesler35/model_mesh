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
-- Core configuration tables
CREATE TABLE providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,           -- 'ollama', 'anthropic', 'google'
    display_name VARCHAR(200),                    -- 'Ollama (Local)', 'Anthropic (Claude)'
    api_base_url VARCHAR(500),                    -- 'http://localhost:11434', null for SDK-based
    auth_type VARCHAR(50) DEFAULT 'bearer',       -- 'bearer', 'api_key', 'none'
    config JSONB DEFAULT '{}',                     -- provider-specific settings
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id UUID REFERENCES providers(id) ON DELETE CASCADE,
    model_id VARCHAR(200) NOT NULL,               -- 'claude-sonnet-4-6', 'gemini-2.5-pro'
    display_name VARCHAR(200),                    -- 'Claude Sonnet 4.6'
    cost_per_1m_input DECIMAL(10,4),              -- Cost per million input tokens
    cost_per_1m_output DECIMAL(10,4),             -- Cost per million output tokens
    context_window INTEGER,                       -- 200000, etc.
    capabilities JSONB DEFAULT '{}',              -- {"vision": true, "streaming": true}
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(provider_id, model_id)
);

CREATE TABLE personas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,                   -- 'Python Architect', 'Quick Helper'
    description TEXT,
    system_prompt TEXT,
    primary_model_id UUID REFERENCES models(id),
    fallback_model_id UUID REFERENCES models(id),
    routing_rules JSONB DEFAULT '{}',             -- {"max_cost": 0.05, "prefer_local": false}
    memory_enabled BOOLEAN DEFAULT true,
    max_memory_messages INTEGER DEFAULT 10,
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Operational tables
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id UUID REFERENCES personas(id),
    external_id VARCHAR(100) UNIQUE,               -- Client-provided conversation ID
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,                    -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    model_used UUID REFERENCES models(id),
    tokens_in INTEGER,
    tokens_out INTEGER,
    latency_ms INTEGER,
    estimated_cost DECIMAL(10,6),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE request_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    persona_id UUID REFERENCES personas(id),
    model_id UUID REFERENCES models(id),
    provider_id UUID REFERENCES providers(id),
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    estimated_cost DECIMAL(10,6),
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed data for default providers
INSERT INTO providers (name, display_name, api_base_url, auth_type) VALUES
    ('ollama', 'Ollama (Local/Cloud)', 'http://localhost:11434', 'none'),
    ('anthropic', 'Anthropic', NULL, 'api_key'),
    ('google', 'Google AI', NULL, 'api_key');
```

### Key Design Decisions

- No `users` table — single-user for MVP, easy to add later
- `personas` are the core abstraction — bundle model choice, system prompt, and routing rules
- `conversations` and `messages` support memory feature
- `request_logs` separate from messages for analytics
- JSONB columns for flexible extension without migrations

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
GET    /v1/personas                    -- List personas
POST   /v1/personas                    -- Create persona
GET    /v1/personas/{id}               -- Get persona details
PATCH  /v1/personas/{id}               -- Update persona
DELETE /v1/personas/{id}               -- Delete persona

GET    /v1/conversations               -- List conversations
GET    /v1/conversations/{id}/messages  -- Get conversation history
DELETE /v1/conversations/{id}           -- Delete conversation

GET    /v1/stats/costs                 -- Cost summary (last N days)
GET    /v1/stats/usage                 -- Token usage breakdown
```

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
    # 1. Resolve persona
    persona = await get_persona(persona_id)
    
    # 2. Build context with memory (if enabled)
    if persona.memory_enabled and conversation_id:
        messages = await memory.get_context(conversation_id, messages, persona.max_memory_messages)
    
    # 3. Apply routing rules
    primary_model = persona.primary_model_id
    fallback_model = persona.fallback_model_id
    
    # Check cost rules
    estimated_tokens = estimate_tokens(messages)
    estimated_cost = calculate_cost(estimated_tokens, primary_model)
    
    if persona.routing_rules.get("max_cost") and estimated_cost > persona.routing_rules["max_cost"]:
        primary_model = fallback_model or raise CostLimitExceeded()
    
    # 4. Try primary model, failover if needed
    try:
        response = await call_model(primary_model, messages, stream=True)
        return response
    except (RateLimitError, TimeoutError, APIError) as e:
        log_error(e, primary_model)
        if fallback_model:
            response = await call_model(fallback_model, messages, stream=True)
            return response
        raise AllModelsFailedError(primary_model, fallback_model, e)
```

### Memory Manager

```python
class MemoryManager:
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def get_context(self, conversation_id: str, new_messages: list, max_messages: int):
        """Retrieve recent message history and append new messages."""
        key = f"conversation:{conversation_id}:messages"
        history = await self.redis.lrange(key, -max_messages, -1)
        history = [json.loads(m) for m in history]
        return history + new_messages
    
    async def store_messages(self, conversation_id: str, messages: list):
        """Persist messages to conversation history."""
        key = f"conversation:{conversation_id}:messages"
        for msg in messages:
            await self.redis.rpush(key, json.dumps(msg))
        await self.redis.expire(key, 86400)  # 24 hours
    
    async def clear_conversation(self, conversation_id: str):
        """Clear conversation memory."""
        await self.redis.delete(f"conversation:{conversation_id}:messages")
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
from litellm import completion

async def call_model(model_id: str, messages: list, stream: bool = True, **params):
    """Call model via LiteLLM with unified interface."""
    model = await get_model(model_id)
    provider = await get_provider(model.provider_id)
    
    # LiteLLM format: "provider/model_name"
    litellm_model = f"{provider.name}/{model.model_id}"
    
    response = await completion(
        model=litellm_model,
        messages=messages,
        stream=stream,
        api_base=provider.api_base_url,
        api_key=get_provider_key(provider.name),
        **params
    )
    
    return response
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

## 9. Docker Compose

```yaml
services:
  postgres:
    image: postgres:16
    volumes: [postgres_data:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: modelmesh
      POSTGRES_USER: modelmesh
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    
  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]
    
  backend:
    build: ./backend
    ports: ["18800:18800"]
    depends_on: [postgres, redis]
    environment:
      DATABASE_URL: postgresql://modelmesh:${POSTGRES_PASSWORD}@postgres/modelmesh
      REDIS_URL: redis://redis:6379
    
  frontend:
    build: ./frontend
    ports: ["18801:3000"]
    depends_on: [backend]

volumes:
  postgres_data:
  redis_data:
```

---

## 10. Configuration

```yaml
# Environment variables
providers:
  ollama:
    base_url: http://localhost:11434
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
  google:
    api_key: ${GOOGLE_API_KEY}

defaults:
  persona: quick-helper
  max_memory_messages: 10
  request_timeout_seconds: 60
```

---

## 11. Future Enhancements (Post-MVP)

- **User authentication** — Multi-user support with API keys
- **Auto-classifier** — Route requests automatically based on content type
- **Billing integration** — Stripe for cost tracking
- **Agent chains** — Sequential model processing
- **IDE plugins** — JetBrains, other editors
- **Advanced analytics** — Cost trends, model performance comparison

---

## 12. Out of Scope for MVP

- Multi-tenant isolation
- Billing/payment integration
- Auto-classification of request types
- User authentication (API keys)
- External Postgres support (Docker only for now)
- Remote Ollama configuration UI (config-file only)