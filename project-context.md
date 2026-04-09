# DevForgeAI — Project Context & AI Rules

> **Date:** April 8, 2026  
> **Project:** AgentMesh / DevForgeAI (Agentic AI Platform)  
> **Status:** Active Development (Phase 2.0)

---

## 1. Project Vision & Goals

### Primary Vision
Transform ModelMesh from a simple API gateway into an **autonomous agentic platform** that:
- Breaks complex user goals into multi-step workflows
- Orchestrates multiple specialized agents working in parallel
- Routes requests to optimal AI models based on cost, performance, and capability
- Maintains persistent user context and learning across sessions
- Generates complete solutions (code, designs, documentation) —not just chat responses

### Core Success Metrics
- **Cost Efficiency:** Use free/local models for simple tasks; reserve expensive models for complex reasoning
- **Zero Vendor Lock-In:** Transparent model abstraction layer
- **Personalization:** Learn from user interactions; maintain context across sessions
- **Reliability:** Self-healing error detection and automatic fallback

---

## 2. Architecture Overview

### System Layers

```
┌─────────────────────────────────────────────┐
│           User Interfaces                   │
│   (Web Chat, API, Voice, File Uploads)      │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│        Agent Orchestrator                   │
│  • Task decomposition                       │
│  • Agent spawning & coordination             │
│  • Memory & context synthesis                │
└─────────────────────────────────────────────┘
                    ↓
┌──────────┬──────────┬──────────┬──────────┐
│  Coder   │Researcher│ Designer │ Reviewer │
│  Agent   │ Agent    │ Agent   │ Agent    │
└──────────┴──────────┴──────────┴──────────┘
                    ↓
┌─────────────────────────────────────────────┐
│    ModelMesh Routing Core                   │
│  • Model routing & failover                 │
│  • Cost bucketing                           │
│  • Token accounting                         │
│  • Context management (Redis/PostgreSQL)    │
└─────────────────────────────────────────────┘
                    ↓
┌──────────┬──────────┬──────────┬──────────┐
│ Claude   │ GPT      │ Gemini   │ Ollama   │
│ (Sonnet) │ (4-Turbo)│(Pro/Nano)│(Local)   │
└──────────┴──────────┴──────────┴──────────┘
```

### Tech Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Backend** | Python 3.11+ / FastAPI | Native AI library support; async-native for streaming |
| **Database** | PostgreSQL | Relational storage for users, personas, memory, config |
| **Cache/Queue** | Redis | Rate limiting, conversation memory, temporary context |
| **Frontend** | React + Next.js | Modern UX, dark mode support, SSR capability |
| **Infrastructure** | Docker Compose | Local LLM support; consistent dev/prod environment |
| **Model Routing** | LiteLLM | Unified interface across Anthropic, OpenAI, Gemini, Ollama |

---

## 3. Project Structure

### Root Level
```
CHARTER.md                    # Project charter & goals
DEVFORGEAI_SPEC.md           # Comprehensive architecture spec
README.md                     # Quick-start guide
start.bat / start-next.js    # Launch scripts
docker-compose.yml           # Local dev environment
```

### `/backend/` — Core Platform

**Key Files:**
- `app/main.py` — FastAPI application entry point
- `app/config.py` — Configuration management (env, secrets)
- `app/database.py` — PostgreSQL connection & session
- `app/redis.py` — Redis cache initialization
- `app/dependencies.py` — Dependency injection (auth, user, etc.)

**Routes:**
- `app/routes/` — API endpoints (personas, models, conversations, agents, etc.)

**Services:**
- `app/services/` — Business logic (model routing, agent orchestration, memory)

**Data Models:**
- `app/models/` — SQLAlchemy ORM models

**Schemas:**
- `app/schemas/` — Pydantic validation schemas for API requests/responses

**Migrations:**
- `alembic/` — Database schema versioning & migrations

### `/frontend/` — Web UI
```
src/
  components/     # React components (Chat, Settings, etc.)
  pages/          # Next.js pages
  styles/         # Tailwind CSS configuration
  api/            # Frontend API client
public/           # Static assets (logos, favicons)
```

### `/tests/` — Test Suite
```
conftest.py       # Pytest fixtures
test_*.py         # Comprehensive test files
e2e/              # End-to-end tests
manual/           # Manual test procedures
reports/          # Test result reports
```

### `/data/` — Persistent Data
```
audit_log.json      # User action audit trail
collab_sessions.json # Collaboration state
collab_users.json    # Collaboration participants
soul.md             # System personality/identity
user.md             # User preferences & profile
projects.json       # Project directory
workspaces.json     # Workspace configurations
context/            # Timestamped session context snapshots
images/             # Generated image metadata
workflows/          # Workflow definitions (Flux, etc.)
```

### `/docs/` — Documentation
```
api.md              # API reference
deployment.md       # Deployment guides
personas.md         # Built-in personas
project-scan-report.json  # Codebase analysis
```

---

## 4. Core Concepts & Terminology

### Persona
A reusable AI "character" with preset configuration:
- **System Prompt:** Defines behavior & context
- **Primary Model:** Preferred model (e.g., Claude Sonnet)
- **Fallback Model:** Secondary option if primary unavailable
- **Routing Rules:** Cost limits, local preference, auto-routing logic
- **Memory:** Persistent conversation history & learned preferences

### Agent
An **autonomous unit of work** dispatched by the Orchestrator:
- **Coder Agent** — Writes, debugs, reviews code
- **Researcher Agent** — Web search, document analysis
- **Designer Agent** — Image generation (Gemini/Flux)
- **Reviewer Agent** — Quality assessment & feedback
- **Planner Agent** — Task decomposition & workflow design
- **Executor Agent** — File I/O, API calls, shell commands
- **Writer Agent** — Documentation, copywriting, summaries

### Workflow
A multi-step process orchestrating multiple agents:
- Triggered by user intent (keywords or direct API call)
- Agents run in parallel when possible (with dependency DAG)
- Results synthesized into final output
- Progress tracked and reported back to user

### Routing
The process of selecting the best model for a request:
- **Cost-based:** Use free/local models first, expensive models only when needed
- **Capability-based:** Route to specialized models (Claude for reasoning, Gemini for images)
- **Failover-based:** Fallback chain if primary model unavailable or rate-limited
- **User Preference-based:** Respect learned persona routing rules

---

## 5. Development Guidelines & AI Rules

### Coding Standards

#### Python Backend
- **Language Version:** Python 3.11+
- **Style Guide:** PEP 8 / Black formatter
- **Type Hints:** Required for all function signatures
- **Async:** Use `async/await` for I/O operations (database, HTTP, Redis)
- **Error Handling:** Use custom exception classes in `app/utils/exceptions.py`
- **Logging:** Use `logging` module; configure in `app/config.py`

#### API Design
- **Prefix:** All routes under `/api/v1/`
- **Naming:** RESTful conventions (POST for create, GET for read, PUT/PATCH for update, DELETE for remove)
- **Responses:** Always return structured JSON with `status`, `data`, `error` fields
- **Pagination:** Use query params `?skip=0&limit=50` for list endpoints
- **Authentication:** JWT tokens from session/middleware injected as `request.user`

#### Database
- **ORM:** SQLAlchemy (sync) + PostgreSQL
- **Migrations:** Use Alembic for schema changes
- **Foreign Keys:** Always defined; cascade delete when appropriate
- **Timestamps:** All tables include `created_at`, `updated_at` (auto-managed)
- **Soft Deletes:** Use `deleted_at` for audit trail (no hard deletes)

#### Testing
- **Framework:** Pytest + async support
- **Coverage Target:** ≥80% for critical paths (routing, auth, model selection)
- **Fixtures:** In `conftest.py`; reuse across test modules
- **Mocking:** Mock external APIs (LiteLLM, Redis, S3)
- **E2E Tests:** Run against live backend; test full workflows

#### Frontend (React/Next.js)
- **Language:** TypeScript (strict mode enabled)
- **Components:** Functional components + hooks only
- **State:** React Context for global state; prefer local state for component-level
- **Styling:** Tailwind CSS utility classes (no custom CSS unless absolutely necessary)
- **API Client:** Centralized in `src/api/client.ts`; use SWR for data fetching
- **Error Handling:** Graceful fallbacks; user-friendly error messages

### Implementation Patterns

#### Adding a New API Endpoint
1. **Define Schema** in `app/schemas/yourfeature.py` (Pydantic model)
2. **Define Model** in `app/models/yourfeature.py` (SQLAlchemy if DB needed)
3. **Create Route** in `app/routes/yourfeature.py` (FastAPI router)
4. **Register Route** in `app/main.py` (include router with prefix)
5. **Add Service Logic** in `app/services/yourfeature.py` (business logic)
6. **Write Tests** in `tests/test_yourfeature.py`
7. **Update Docs** in `docs/api.md`

#### Adding a New Agent Type
1. **Define Agent Config** in `app/models/agent.py`
2. **Create Agent Class** in `app/services/agents/yourAgent.py` (inherit from `BaseAgent`)
3. **Implement Methods:**
   - `async execute(task: Task) → Result`
   - `async validate_capability(task: Task) → bool`
   - `get_system_prompt() → str`
4. **Register in Orchestrator** in `app/services/orchestrator.py`
5. **Add Tests:** `tests/test_agents.py`
6. **Update Schema:** `app/schemas/agents.py`

#### Model Routing Decision
**Logic Flow:**
1. User sets persona (or use default)
2. Check persona's routing rules:
   - If `prefer_local=true` and task is simple → use Ollama/local
   - If `max_cost` budget set → filter expensive models
   - If `auto_route=true` → use classifier persona to pick best model
3. Fall back to persona's `primary_model_id`
4. If unavailable, try `fallback_model_id`
5. If still unavailable, error + alert ops team

---

## 6. AI Agent Interaction Rules

When agents (external or internal) interact with this codebase, follow these principles:

### For Code Generation Tasks

**DO:**
- Follow existing code patterns and import conventions
- Use type hints and docstrings for all functions
- Write async functions for I/O operations
- Add error handling with try/except + logging
- Include tests for new functionality
- Update relevant docs and API schema files
- Use existing service layer architecture (don't bypass it)

**DON'T:**
- Bypass SQLAlchemy; write direct SQL queries
- Introduce new dependencies without discussing trade-offs
- Commit to `main` directly; create feature branches
- Ignore existing test patterns; use pytest fixtures
- Hardcode configuration; use `app/config.py`
- Leave TODOs or incomplete implementations

### For Debugging Tasks

**DO:**
- Check application logs first (`logs/` directory or stdout)
- Use the test suite to reproduce issues locally
- Check recent commits in git history (`last_good_commit.txt`)
- Verify database state using `check_db.py`
- Cross-reference with health status (`health_status.json`)

**DON'T:**
- Modify production data without rollback plan
- Skip writing test case to reproduce the bug
- Change multiple systems simultaneously
- Ignore error context or stack traces

### For Architecture/Design Tasks

**DO:**
- Reference DEVFORGEAI_SPEC.md and CHARTER.md for authority
- Propose changes via discussion before implementation
- Consider impact on existing personas and workflows
- Parallelize work when possible (agents → routes → services)
- Use dependency injection for testability

**DON'T:**
- Redesign core systems without requirements clarity
- Add breaking changes to API contracts
- Ignore existing ORM relationships and constraints
- Design without considering scalability implications

---

## 7. Current Status & Key Metrics

### Completed (Phase 1.0)
✅ Core FastAPI gateway  
✅ PostgreSQL data layer  
✅ Redis caching layer  
✅ LiteLLM model routing  
✅ User authentication (JWT)  
✅ Persona system  
✅ Basic conversations endpoint  
✅ Docker Compose deployment  

### In Progress (Phase 2.0)
🔄 Agent Orchestrator framework  
🔄 Parallel agent execution  
🔄 Workflow engine  
🔄 Memory synthesis  
🔄 Web UI improvements  
🔄 E2E testing suite  

### Backlog (Phase 3.0 & Beyond)
⏳ Image generation agents (Flux/Gemini)  
⏳ Voice input/output  
⏳ Collaboration (shared workspaces, @mentions)  
⏳ Custom agent creation UI  
⏳ Kubernetes deployment  
⏳ Analytics dashboard  

### Key Commit References
- `last_good_commit.txt` — Stable reference point
- Health checks: `health_status.json`
- Database verification: `check_db.py`
- Test coverage: `tests/reports/`

---

## 8. Running the Project Locally

### Prerequisites
- Python 3.11+
- Docker / Docker Compose
- Node.js 18+
- PostgreSQL 15+ (or via Docker)
- Redis (or via Docker)

### Quick Start
```bash
# Start all services (Docker)
./start.bat

# Backend dev server (runs separately)
cd backend && python -m uvicorn app.main:app --reload

# Frontend dev server (runs separately)
cd frontend && npm run dev

# Run tests
cd tests && pytest -v

# Check database health
python check_db.py
```

### Environment Variables
Create `.env` in backend directory:
```
DATABASE_URL=postgresql://user:password@localhost:5432/devforgeai
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
```

---

## 9. Critical Success Factors for AI Agents

1. **Understand Context:** Always read CHARTER.md + DEVFORGEAI_SPEC.md before proposing changes
2. **Maintain Conventions:** Follow existing patterns (routing structure, service layer, schema validation)
3. **Test First:** Write tests before or alongside implementation
4. **Document Changes:** Update API docs, schema files, and architectural diagrams
5. **Ask Before Major Changes:** Changes to core systems (routing, auth, ORM) require discussion
6. **Atomic Commits:** Each commit should represent one logical change with clear purpose
7. **Reference Authority:** Link decisions to CHARTER.md or DEVFORGEAI_SPEC.md for justification

---

## 10. Quick Reference: Key Files to Know

| File | Purpose | When to Edit |
|------|---------|--------------|
| `app/main.py` | FastAPI app setup | Adding new routes/middleware |
| `app/config.py` | Configuration | Adding config vars |
| `app/models/` | ORM definitions | New database tables |
| `app/routes/` | API endpoints | New API endpoints |
| `app/services/` | Business logic | New features |
| `app/schemas/` | Validation | Updating API contracts |
| `alembic/versions/` | DB migrations | Schema changes |
| `tests/conftest.py` | Test fixtures | New test utilities |
| `DEVFORGEAI_SPEC.md` | Architecture authority | Never (reference only) |
| `CHARTER.md` | Project charter | Never (reference only) |

---

## 11. Support & References

- **Architecture:** See DEVFORGEAI_SPEC.md
- **Requirements:** See CHARTER.md
- **API Reference:** See docs/api.md
- **Test Results:** See tests/reports/
- **Deployment:** See docs/deployment.md
- **Personas:** See docs/personas.md

---

**Last Updated:** April 8, 2026  
**Maintained By:** Development Team  
**Next Review:** After Phase 2.0 completion
