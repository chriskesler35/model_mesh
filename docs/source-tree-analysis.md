# Source Tree Analysis

Annotated directory structure of the DevForgeAI (ModelMesh) monorepo. Each entry includes a description of its role and contents.

---

```
Model_Mesh/
├── backend/                        # Python FastAPI backend (central hub)
│   ├── app/
│   │   ├── main.py                 # FastAPI app entry point; lifespan setup (DB init,
│   │   │                           #   seeding, migration); CORS; middleware registration
│   │   ├── config.py               # Pydantic BaseSettings — loads .env, defines all
│   │   │                           #   config (DB URL, API keys, feature flags, ports)
│   │   ├── database.py             # SQLAlchemy async engine + session factory;
│   │   │                           #   supports SQLite (local) and PostgreSQL (Docker)
│   │   ├── dependencies.py         # FastAPI dependency injection (get_db, get_current_user,
│   │   │                           #   require_admin, get_redis)
│   │   ├── redis.py                # Redis client singleton; graceful fallback when
│   │   │                           #   Redis is unavailable
│   │   ├── seed.py                 # Database seeding — creates default providers,
│   │   │                           #   models, personas, and admin user on first run
│   │   ├── migrate.py              # Runtime SQLite migration logic; applies schema
│   │   │                           #   changes without requiring Alembic in dev mode
│   │   │
│   │   ├── middleware/
│   │   │   ├── auth.py             # API key + JWT authentication middleware;
│   │   │   │                       #   validates Bearer tokens, resolves user context
│   │   │   └── rate_limit.py       # Redis-backed rate limiter; per-key request
│   │   │                           #   throttling with configurable windows
│   │   │
│   │   ├── models/                 # 18 SQLAlchemy ORM models defining the full
│   │   │                           #   data schema: User, Conversation, Message,
│   │   │                           #   Provider, Model, Persona, Project, Task,
│   │   │                           #   WorkbenchSession, Pipeline, PipelinePhase,
│   │   │                           #   APIKey, UsageRecord, Workspace, ShareLink, etc.
│   │   │
│   │   ├── routes/                 # 33 route groups organized by domain:
│   │   │                           #   - chat.py: /v1/chat/completions (streaming + sync)
│   │   │                           #   - conversations.py: CRUD for conversations
│   │   │                           #   - personas.py: persona management
│   │   │                           #   - models.py: model registry
│   │   │                           #   - providers.py: provider configuration
│   │   │                           #   - projects.py: project management + sandbox
│   │   │                           #   - workbench.py: single-agent workbench sessions
│   │   │                           #   - pipelines.py: multi-agent pipeline orchestration
│   │   │                           #   - tasks.py: async task queue (image gen, etc.)
│   │   │                           #   - images.py: image generation endpoints
│   │   │                           #   - auth.py: login, register, token refresh
│   │   │                           #   - api_keys.py: API key management
│   │   │                           #   - users.py: user administration
│   │   │                           #   - health.py: health check endpoint
│   │   │                           #   - model_sync.py: sync models from providers
│   │   │                           #   - model_validate.py: model fitness validation
│   │   │                           #   - identity.py: AI identity file management
│   │   │                           #   - usage.py: cost tracking and analytics
│   │   │                           #   - share.py: public share link generation
│   │   │                           #   - (and more)
│   │   │
│   │   ├── schemas/                # Pydantic request/response schemas; mirrors the
│   │   │                           #   route structure with Create, Update, and
│   │   │                           #   Response variants for each domain
│   │   │
│   │   ├── services/               # 16 service modules containing business logic:
│   │   │                           #   - chat_service.py: LLM call orchestration
│   │   │                           #   - persona_service.py: persona resolution + fallback
│   │   │                           #   - model_client.py: LiteLLM wrapper
│   │   │                           #   - workbench_service.py: agent loop + tool dispatch
│   │   │                           #   - pipeline_service.py: multi-agent phase runner
│   │   │                           #   - project_service.py: sandbox + file ops
│   │   │                           #   - image_service.py: Gemini Imagen + ComfyUI
│   │   │                           #   - auth_service.py: JWT + password hashing
│   │   │                           #   - usage_service.py: cost aggregation
│   │   │                           #   - snapshot_service.py: state capture + rollback
│   │   │                           #   - hardware_service.py: GPU/VRAM monitoring
│   │   │                           #   - (and more)
│   │   │
│   │   ├── scripts/                # Standalone utility scripts:
│   │   │                           #   - seed_db.py: manual database seeding
│   │   │                           #   - create_tables.py: schema creation without app
│   │   │
│   │   └── utils/                  # Utility module (placeholder for shared helpers)
│   │
│   ├── alembic/                    # Alembic database migration directory:
│   │   ├── versions/               #   Migration scripts (PostgreSQL deployments)
│   │   ├── env.py                  #   Migration environment config
│   │   └── alembic.ini             #   Alembic configuration
│   │
│   ├── tests/                      # Backend unit and integration tests
│   ├── requirements.txt            # Python dependencies (pinned versions)
│   ├── pyproject.toml              # Project config + pytest settings
│   └── Dockerfile                  # Backend container image (Python 3.11-slim)
│
├── frontend/                       # Next.js 14 web frontend
│   ├── src/
│   │   ├── app/                    # App Router pages (34 files total):
│   │   │   ├── (main)/             # Sidebar layout group — pages with navigation:
│   │   │   │   ├── page.tsx        #   Dashboard (home)
│   │   │   │   ├── agents/         #   Agent/persona management UI
│   │   │   │   ├── models/         #   Model registry browser
│   │   │   │   ├── personas/       #   Persona configuration
│   │   │   │   ├── providers/      #   Provider status and setup
│   │   │   │   ├── projects/       #   Project list and detail views
│   │   │   │   ├── images/         #   Image generation gallery
│   │   │   │   ├── settings/       #   App settings (API keys, identity, preferences)
│   │   │   │   ├── usage/          #   Cost tracking and usage analytics
│   │   │   │   └── workbench/      #   Workbench UI:
│   │   │   │       ├── page.tsx    #     Session list
│   │   │   │       ├── [id]/       #     Single-agent session view
│   │   │   │       └── pipelines/  #     Multi-agent pipeline swim-lane UI
│   │   │   │           └── [id]/   #       Individual pipeline detail
│   │   │   │
│   │   │   ├── chat/               # Full-screen chat interface (2256 lines);
│   │   │   │                       #   streaming, markdown, inline images, persona picker
│   │   │   ├── login/              # Login page (username + password or API key)
│   │   │   ├── share/              # Public share viewer (read-only conversation view)
│   │   │   ├── auth/               # OAuth callback handlers:
│   │   │   │   └── openrouter/     #   OpenRouter OAuth flow completion
│   │   │   │       └── callback/
│   │   │   └── api/                # Next.js API routes (server-side):
│   │   │       ├── backend/        #   Backend proxy
│   │   │       ├── health/         #   Frontend health check
│   │   │       └── readme/         #   README content server
│   │   │
│   │   ├── components/             # 5 reusable React components:
│   │   │                           #   Sidebar, InlineImage, MarkdownRenderer,
│   │   │                           #   CodeBlock, ErrorBoundary
│   │   │
│   │   └── lib/                    # Shared library code:
│   │       ├── config.ts           #   Runtime config (API URL detection)
│   │       ├── api.ts              #   Backend API client with auth headers
│   │       ├── types.ts            #   TypeScript type definitions
│   │       ├── markdown.ts         #   Markdown parsing and rendering utilities
│   │       └── openrouter-oauth.ts #   OpenRouter OAuth flow helpers
│   │
│   ├── public/                     # Static assets (favicon, logos)
│   ├── package.json                # npm config + scripts (dev, build, start)
│   ├── tailwind.config.ts          # Tailwind CSS configuration
│   ├── tsconfig.json               # TypeScript compiler options
│   ├── next.config.js              # Next.js configuration
│   └── Dockerfile                  # Frontend container image (Node 18-alpine)
│
├── extension/                      # VS Code extension for IDE integration
│   ├── src/
│   │   ├── extension.ts            # Entry point; registers commands, activates
│   │   │                           #   providers, sets up disposables
│   │   ├── commands/
│   │   │   ├── sendSelection.ts    # Send selected code to backend for analysis
│   │   │   └── newConversation.ts  # Start a new conversation from VS Code
│   │   ├── providers/
│   │   │   └── PersonaProvider.ts  # TreeDataProvider for sidebar persona list
│   │   ├── api/
│   │   │   └── ModelMeshClient.ts  # REST + SSE client for backend communication
│   │   └── utils/
│   │       └── config.ts           # VS Code settings reader (apiUrl, apiKey)
│   │
│   ├── package.json                # Extension manifest (contributes: commands,
│   │                               #   views, configuration, menus)
│   ├── tsconfig.json               # TypeScript config for extension
│   └── .vscodeignore               # Files excluded from VSIX package
│
├── data/                           # Runtime data directory (gitignored contents):
│   ├── devforgeai.db               #   SQLite database (single source of truth)
│   ├── soul.md                     #   AI personality definition
│   ├── user.md                     #   User context and preferences
│   ├── identity.md                 #   Runtime identity configuration
│   ├── images/                     #   Generated images storage
│   ├── workflows/                  #   ComfyUI workflow JSON templates
│   ├── snapshots/                  #   System state snapshots for rollback
│   └── context/                    #   Project context captures
│
├── tests/                          # Root-level integration tests (20 test files):
│                                   #   End-to-end tests covering API contracts,
│                                   #   auth flows, chat streaming, workbench,
│                                   #   pipelines, image generation, and more
│
├── docs/                           # Project documentation:
│   ├── project-overview.md         #   Executive project summary
│   ├── integration-architecture.md #   Inter-component communication docs
│   ├── source-tree-analysis.md     #   This file — annotated source tree
│   ├── api-contracts-backend.md    #   Backend API endpoint reference
│   ├── architecture-backend.md     #   Backend architecture deep-dive
│   ├── api.md                      #   API usage guide
│   ├── deployment.md               #   Deployment instructions
│   ├── personas.md                 #   Persona system documentation
│   └── superpowers/                #   SuperPowers methodology docs
│
├── devforgeai.py                   # CLI runner script:
│                                   #   `python devforgeai.py start` — launch backend + frontend
│                                   #   `python devforgeai.py stop`  — graceful shutdown
│                                   #   `python devforgeai.py status` — check running processes
│
├── install.py                      # Cross-platform installer:
│                                   #   Detects OS, installs Python/Node deps,
│                                   #   creates .env from template, initializes DB
│
├── docker-compose.yml              # Docker Compose stack:
│                                   #   - backend (FastAPI on 18800)
│                                   #   - frontend (Next.js on 18801)
│                                   #   - postgres (15432)
│                                   #   - redis (16379)
│
├── ecosystem.config.js             # PM2 process manager configuration:
│                                   #   Defines backend + frontend as managed processes
│                                   #   with log rotation and restart policies
│
├── start.bat                       # Windows batch launcher (double-click to start)
├── Start-DevForgeAI.ps1            # PowerShell launcher with admin elevation
│
├── .env                            # Environment variables (API keys, DB URLs,
│                                   #   feature flags) — not committed to git
├── .env.example                    # Template for .env with all available options
├── .gitignore                      # Git ignore rules
└── package.json                    # Root package.json (workspace scripts)
```

---

## Critical Directories Explained

### `backend/app/models/`

Contains 18 SQLAlchemy ORM models that define the complete database schema. Every table in the SQLite/PostgreSQL database has a corresponding model here. Models use async-compatible column types and include relationships for eager/lazy loading.

### `backend/app/routes/`

Contains 33 route modules, each mounted as a FastAPI `APIRouter`. Routes handle request validation (via Pydantic schemas), call into services for business logic, and return responses. SSE endpoints use `StreamingResponse` with `text/event-stream` content type.

### `backend/app/services/`

Contains 16 service modules that encapsulate all business logic. Routes delegate to services, which in turn use the ORM models and external APIs. This separation keeps routes thin and services testable. The most complex services are `chat_service.py` (LLM orchestration), `workbench_service.py` (agentic tool-use loop), and `pipeline_service.py` (multi-phase orchestration).

### `frontend/src/app/`

Uses Next.js 14 App Router conventions. The `(main)/` route group applies the sidebar layout to all pages within it. Each subdirectory represents a page or nested route. Pages are a mix of server components (data fetching) and client components (interactivity, SSE).

### `frontend/src/lib/`

Shared library code used across all frontend pages and components. The `config.ts` file handles runtime API URL detection. The `api.ts` file provides a configured fetch wrapper with authentication headers.

### `data/`

Runtime data directory created on first launch. Contains the SQLite database, AI identity files, generated images, ComfyUI workflows, and system snapshots. Contents are gitignored except for example/template files. This directory is the primary state store for local deployments.

### `tests/`

Root-level integration tests that exercise the full stack. These tests start the backend, make HTTP requests, and verify responses. They cover API contracts, authentication flows, streaming, workbench sessions, pipelines, and image generation.
