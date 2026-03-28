# Project Charter: DevForgeAI (Agentic AI Platform)

## 1. Project Overview

**Vision:** To create a unified API interface that intelligently routes development requests to the optimal AI model, balancing cost, performance, and capability. The system should learn from user interactions and personalize responses over time.

**Primary Goal:** Reduce AI operational costs by utilizing local/free models for simple tasks while reserving expensive proprietary models for complex reasoning.

**Secondary Goal:** Prevent vendor lock-in by abstracting the provider layer.

**Tertiary Goal:** Provide a "smarter" AI experience where the system learns user preferences, maintains context across sessions, and can self-heal from errors.

## 2. Technical Architecture

We use a **Modular Monolith** architecture (easier to develop/test) which can be split into microservices later.

### Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Backend Language | Python (FastAPI) | Python is the native language of AI. Libraries like litellm are Python-first. Handles async requests natively (crucial for streaming). |
| Database | PostgreSQL | Relational data for user configs, API keys, personas, memory files, preferences. |
| Cache/Queue | Redis | Rate limiting, conversation memory, temporary context storage. |
| Frontend | React + Next.js | Modern UI with dark mode, client-side rendering for better UX. |
| Infrastructure | Docker | Essential for local LLM containers and consistent deployment. |

### System Diagram

```
User Client → ModelMesh API Gateway → Router Engine
                                              ↓
                    ┌──────────────────────────┼───────────────────────┐
                    ↓                          ↓                       ↓
              Anthropic Adapter          OpenAI Adapter          Ollama Adapter
                    ↓                          ↓                       ↓
              Claude Models              GPT Models              Local Models
```

## 3. Database Schema Design

### Core Tables

#### users
- id (UUID)
- email, password_hash
- default_persona_id
- preferences (JSON)

#### providers
- id (UUID)
- name, display_name
- api_base_url
- auth_type
- is_active

#### models
- id (UUID)
- provider_id (FK)
- model_id, display_name
- cost_per_1m_input, cost_per_1m_output
- context_window
- capabilities (JSON)
- is_active
- updated_at

#### personas
- id (UUID)
- name, description
- system_prompt
- primary_model_id (FK), fallback_model_id (FK)
- routing_rules (JSON) - max_cost, prefer_local, auto_route, classifier_persona_id
- memory_enabled, max_memory_messages
- is_default
- updated_at

#### conversations
- id (UUID)
- persona_id (FK)
- external_id
- created_at, updated_at

#### messages
- id (UUID)
- conversation_id (FK)
- role, content
- created_at

#### request_logs
- id (UUID)
- conversation_id, persona_id, model_id, provider_id
- input_tokens, output_tokens
- latency_ms, estimated_cost
- success, error_message
- created_at

### Personalization Tables (NEW)

#### user_profiles
- id (UUID)
- name, email
- preferences (JSON)
- is_active
- created_at, updated_at

#### memory_files
- id (UUID)
- user_id (FK)
- name (e.g., "USER.md", "CONTEXT.md")
- content (TEXT)
- description
- created_at, updated_at

#### preference_tracking
- id (UUID)
- user_id (FK)
- key, value
- source (chat/manual/system)
- confidence (low/medium/high)
- context (TEXT)
- created_at

#### system_modifications
- id (UUID)
- user_id (FK)
- conversation_id (FK)
- modification_type, entity_type
- entity_id
- before_value, after_value (JSON)
- reason (TEXT)
- created_at

## 4. Development Phases

### Phase 1: Core & Local Integration ✅ COMPLETE
- Docker Compose setup
- Database migrations
- BaseModelAdapter pattern
- Ollama adapter
- POST /v1/chat endpoint

### Phase 2: Multi-Provider Logic ✅ COMPLETE
- OpenAI, Anthropic, Google, OpenRouter adapters
- Unified response format (OpenAI-compatible)
- Routing engine with failover
- Cost estimation and checking

### Phase 3: Intelligence & Personas ✅ COMPLETE
- Persona CRUD (API + UI)
- Context management (Redis memory)
- Auto-router classifier (CODE/MATH/CREATIVE/SIMPLE/ANALYSIS)
- Frontend dashboard with stats

### Phase 4: Resilience & Testing ✅ COMPLETE
- Integration tests
- Rate limiting (Redis sliding window)
- Streaming support (SSE)
- API documentation (Swagger)

### Phase 5: Personalization & Learning ✅ COMPLETE
- User profiles
- Memory files (USER.md, CONTEXT.md, PREFERENCES.md)
- Preference tracking from chat
- System modification tracking
- Context injection into system prompts

### Phase 6: UI/UX Polish ✅ COMPLETE
- Dark/Light mode toggle
- Settings page with memory file editor
- Persona create/edit forms
- Model CRUD (add/delete/toggle)
- Provider names in model list

### Phase 7: Self-Healing & Recovery ✅ COMPLETE
- Health check endpoint (database, Redis, disk, processes)
- Snapshot creation (config files, git commits)
- Automatic recovery attempts
- Manual rollback to snapshots
- Last known good commit tracking

### Phase 8: Model Management ✅ COMPLETE
- Add/delete models via UI ✅
- Toggle model active status ✅
- Auto-update personas when model deleted ✅
- Provider dropdown populated from API ✅
- Provider names display correctly ✅

## 5. API Endpoints

### Core Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | /v1/chat/completions | Chat completion (streaming supported) |
| GET | /v1/models | List all models |
| POST/PATCH/DELETE | /v1/models | Model CRUD |
| GET | /v1/providers | List all providers |
| GET/POST/PATCH/DELETE | /v1/personas | Persona CRUD |
| GET/POST | /v1/conversations | Conversation management |
| GET | /v1/stats/costs | Cost analytics |
| GET | /v1/stats/usage | Usage analytics |

### Personalization Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/PATCH | /v1/user | User profile |
| GET/POST/PATCH/DELETE | /v1/memory | Memory files |
| GET/POST/DELETE | /v1/preferences | Learned preferences |
| GET | /v1/modifications | Modification history |

### System Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /v1/system/health | Health check |
| POST | /v1/system/snapshots | Create snapshot |
| GET | /v1/system/snapshots | List snapshots |
| POST | /v1/system/recover | Trigger recovery |
| POST | /v1/system/rollback/{name} | Rollback to snapshot |

## 6. Frontend Pages

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | / | Stats overview, quick actions |
| Personas | /personas | List all personas |
| New Persona | /personas/new | Create/edit persona |
| Models | /models | List all models, add/delete/toggle |
| Conversations | /conversations | Conversation history |
| Stats | /stats | Usage and cost analytics |
| Settings | /settings | Profile, memory files, preferences |
| Chat | /chat | Chat interface |

## 7. Key Features

### Intelligent Routing
- Auto-router classifies requests (CODE/MATH/CREATIVE/SIMPLE/ANALYSIS)
- Routes to optimal model based on classification
- Cost-aware routing (blocks expensive requests over limit)
- Failover from primary to fallback model

### Personalization
- Memory files injected into system prompts
- Preference tracking from chat interactions
- User profile with customizable settings
- System modification tracking (audit trail)

### Self-Healing
- Health checks for all critical components
- Automatic recovery attempts
- Snapshot-based rollback
- Git commit tracking for code rollback

### Developer Experience
- OpenAI-compatible API
- Swagger documentation
- Rate limiting with clear headers
- Streaming responses (SSE)
- Comprehensive error messages

## 8. Future Extensions

- **Agent Chains:** Pipeline models (Writer → Reviewer)
- **Billing:** Stripe integration for token billing
- **IDE Plugin:** VS Code extension
- **Chat Self-Modification:** Add/update models/personas via chat commands
- **Advanced Learning:** Preference reinforcement from user feedback
- **Multi-user Support:** Auth, roles, per-user settings

## 9. Models & Providers

### Current Providers
| Provider | Models | Cost Range |
|----------|--------|-------------|
| Ollama (Local) | Llama 3.1 8B, GLM-5 Cloud, Qwen 2.5 Coder 14B | Free |
| Anthropic | Claude Sonnet 4.6, Claude Opus 4.6 | $3-75/1M tokens |
| Google | Gemini 2.5 Pro, Gemini 3.1 Pro Preview | $1.25-5/1M tokens |
| OpenRouter | Claude, GPT-4.1, Gemini via OpenRouter | Variable |

### Default Personas
| Persona | Primary Model | Use Case |
|---------|---------------|----------|
| quick-helper | Llama 3.1 8B | Simple tasks, local-first |
| classifier | Llama 3.1 8B | Request classification |
| python-architect | Claude Sonnet 4.6 | Code review, architecture |
| smart-router | Claude Sonnet 4.6 | Auto-routing enabled |
| glm-coder | GLM-5 Cloud | Free coding assistance |

## 10. Configuration

### Environment Variables
| Variable | Description |
|----------|-------------|
| DATABASE_URL | PostgreSQL connection string |
| REDIS_URL | Redis connection string |
| ANTHROPIC_API_KEY | Anthropic API key |
| GOOGLE_API_KEY | Google AI API key |
| OPENROUTER_API_KEY | OpenRouter API key |
| OLLAMA_BASE_URL | Ollama API base URL (default: http://localhost:11434) |
| MODELMESH_API_KEY | API key for ModelMesh API |

### Rate Limits
- Default: 60 requests/minute, 1000 requests/hour per API key
- Configurable in `app/config.py`