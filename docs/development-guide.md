# Development Guide

## Prerequisites

| Requirement | Version | Check Command |
|-------------|---------|---------------|
| Python | 3.11+ | `python --version` |
| Node.js | 18+ | `node --version` |
| npm | (bundled with Node) | `npm --version` |
| Git | any recent | `git --version` |

### Optional
| Tool | Purpose |
|------|---------|
| Ollama | Local AI models (free, no API key) |
| ComfyUI | Local image generation |
| Redis | Conversation memory cache + rate limiting |
| PostgreSQL | Production database (Docker) |

## Installation

### Automated
```bash
python install.py
```
This will:
1. Check Python 3.11+ and Node.js 18+
2. Create Python virtual environment (`backend/venv/`)
3. Install Python dependencies (`backend/requirements.txt`)
4. Install npm packages (`frontend/node_modules/`)
5. Create `.env` from `.env.example`
6. Create start scripts

### Manual
```bash
# Backend
cd backend
python -m venv venv
venv/Scripts/activate   # Windows
source venv/bin/activate # macOS/Linux
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

## Environment Setup

Copy and edit `.env`:
```bash
cp .env.example .env
```

### Required Variables
At minimum, configure ONE AI provider API key:
| Variable | Provider |
|----------|----------|
| `ANTHROPIC_API_KEY` | Anthropic (Claude) |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | Google (Gemini) |
| `OPENROUTER_API_KEY` | OpenRouter (multi-model) |
| `OPENAI_API_KEY` | OpenAI |

Or use Ollama (local, free — no key needed):
```
OLLAMA_BASE_URL=http://localhost:11434
```

### Optional Variables
| Variable | Default | Purpose |
|----------|---------|---------|
| `MODELMESH_API_KEY` | `modelmesh_local_dev_key` | Master API key |
| `TELEGRAM_BOT_TOKEN` | (none) | Telegram bot integration |
| `TELEGRAM_CHAT_IDS` | (none) | Allowed Telegram chat IDs |
| `GITHUB_CLIENT_ID` | (none) | GitHub OAuth |
| `GITHUB_CLIENT_SECRET` | (none) | GitHub OAuth |
| `COMFYUI_URL` | `http://localhost:8188` | ComfyUI for local image gen |

## Running

### Option 1: CLI Runner
```bash
python devforgeai.py start           # Start both
python devforgeai.py start backend   # Backend only
python devforgeai.py start frontend  # Frontend only
python devforgeai.py stop            # Stop all
python devforgeai.py status          # Check status
```

### Option 2: Start Scripts
- **Windows**: `start.bat` or `Start-DevForgeAI.ps1`
- **macOS/Linux**: `./start.sh`

### Option 3: PM2
```bash
npm install -g pm2
pm2 start ecosystem.config.js
pm2 logs
```

### Option 4: Docker (with PostgreSQL + Redis)
```bash
docker-compose up -d
```
Docker port mapping: Backend 19000→18800, Frontend 3001→18801, PostgreSQL 15432, Redis 16379

### URLs
| Service | Local Dev | Docker |
|---------|-----------|--------|
| Frontend | http://localhost:3001 | http://localhost:18801 |
| Backend | http://localhost:19001 | http://localhost:19000 |
| API Docs | http://localhost:19001/docs | http://localhost:19000/docs |

## Development Workflow

### Backend Development
```bash
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
uvicorn app.main:app --host 0.0.0.0 --port 19001 --reload
```
- Auto-reload enabled via `--reload`
- FastAPI Swagger docs at `/docs`
- Database auto-creates tables + runs migrations on startup
- Auto-seeds providers, models, personas on first run

### Frontend Development
```bash
cd frontend
npm run dev
```
- Runs on port 3001 with hot-reload
- Auto-detects backend at `{hostname}:19001` for local development
- `npm run build` for production build
- `npm run lint` for ESLint

### Extension Development
```bash
cd extension
npm run compile     # One-time build
npm run watch       # Watch mode
```
- Press F5 in VS Code to launch Extension Development Host
- Output in `dist/`

## Testing

### Backend Tests
```bash
cd backend
source venv/bin/activate
pytest                       # Run all tests
pytest -v                    # Verbose
pytest -m "not slow"         # Skip LLM-calling tests
pytest --cov=app             # With coverage
```

### Root Integration Tests
Requires a running backend:
```bash
cd tests
pip install -r requirements.txt
pytest                       # Run all
pytest test_chat.py          # Specific module
pytest -m "not destructive"  # Skip destructive tests
```
Test modules: test_agents, test_chat, test_collaboration, test_conversations, test_health, test_identity, test_images, test_methods, test_misc, test_models, test_personas, test_preferences, test_projects, test_remote, test_settings, test_stats, test_workbench, test_workflows

### Custom Markers
- `@pytest.mark.slow` — tests that call an LLM
- `@pytest.mark.destructive` — tests that modify significant state

## Build Process

### Frontend Production Build
```bash
cd frontend
npm run build    # Creates .next/ standalone output
npm run start    # Serve production build on port 3001
```

### Extension Packaging
```bash
cd extension
npm run compile           # TypeScript -> dist/
npx vsce package          # Create .vsix
npx vsce publish          # Publish to marketplace
```

### Docker Build
```bash
docker-compose build      # Build all services
docker-compose up -d      # Run detached
docker-compose logs -f    # Follow logs
```

## Database

- **Local dev**: SQLite at `data/devforgeai.db` (zero config)
- **Docker/Production**: PostgreSQL 16
- **Migrations**: Alembic (PostgreSQL) + runtime ALTER TABLE (SQLite)
- **Seeding**: Automatic on first startup (4 providers, 12 models, 3 personas)

## Project Structure Quick Reference

| Path | Purpose |
|------|---------|
| `backend/app/routes/` | API endpoints (33 groups) |
| `backend/app/models/` | Database models (18 tables) |
| `backend/app/services/` | Business logic (16 services) |
| `backend/app/schemas/` | Request/response validation |
| `frontend/src/app/` | Next.js pages and layouts |
| `frontend/src/components/` | Reusable UI components |
| `frontend/src/lib/` | API client, config, types |
| `extension/src/` | VS Code extension source |
| `data/` | Runtime data (DB, images, identity, workflows) |
| `tests/` | Integration test suite |
| `docs/` | Project documentation |
