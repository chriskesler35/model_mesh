# DevForgeAI

An intelligent AI development platform for multi-agent orchestration, image generation, and workflow automation. Built with FastAPI + Next.js 14.

---

## What It Does

- **Chat** with local Ollama models and cloud providers (Anthropic, Google, OpenRouter, OpenAI) through a single interface
- **Agents** that can code, research, design, review, plan, and write - each backed by a persona
- **Image Generation** via Gemini Imagen or ComfyUI with workflow selection, checkpoint picker, and gallery management
- **Telegram Bot** - chat with your AI, generate images, and get notifications remotely
- **Identity System** - the AI learns who you are (SOUL.md + USER.md) and injects context into every session
- **Session Snapshots** - every conversation is snapshotted to disk; broken/compacted sessions recover automatically
- **Rolling Memory** - MEMORY.md accumulates distilled insights across all conversations over time
- **Live Workbench** - watch agents work in real-time, intervene mid-task, replay past sessions
- **Projects** - point agents at any directory; per-project venvs, git snapshots, rollbacks
- **Development Methods** - BMAD, GSD, SuperPowers, GTrack (stackable)
- **Learned Preferences** - the AI detects your preferences from chat and applies them automatically
- **Remote Access** - access from any device on your network or Tailscale; frontend auto-detects the backend URL
- **Settings UI** - manage API keys, providers, ComfyUI paths, image generation, server health, and more

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11-3.13, FastAPI, SQLite (aiosqlite), LiteLLM |
| Frontend | Next.js 14, React 18, TailwindCSS |
| AI Providers | Ollama (local), Anthropic, Google Gemini, OpenRouter, OpenAI |
| Image Gen | Gemini Imagen, ComfyUI |
| Ports | Backend: 19000 · Frontend: 3001 |

---

## Quick Start

### Prerequisites

- **Python 3.11, 3.12, or 3.13** - https://www.python.org/downloads/
- **Node.js 18+** - https://nodejs.org/
- At least one AI provider key, *or* [Ollama](https://ollama.ai) installed locally (no key needed)

### 1. Clone

```bash
git clone https://github.com/chriskesler35/model_mesh.git
cd model_mesh
```

### 2. Backend setup

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure

Copy the example env file and fill in your keys:

```bash
cp .env.example .env   # or create backend/.env manually
```

Minimum `.env` to get started:

```env
# At least one of these - or just run Ollama locally
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
GEMINI_API_KEY=AIza...        # same key as GOOGLE_API_KEY works
OPENROUTER_API_KEY=sk-or-v1-...
OPENAI_API_KEY=sk-...

# Ollama (if installed locally - no key needed)
OLLAMA_BASE_URL=http://localhost:11434

# App auth key (change this in production)
MODELMESH_API_KEY=modelmesh_local_dev_key

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_IDS=
```

### 4. Frontend setup

```bash
cd ../frontend
npm install
```

### 5. Start

**Option A - Background, no windows (recommended on Windows):**
```
# Install PM2 once
npm install -g pm2
pm2 set pm2:windowsHide true

# Then just double-click:
start-hidden.vbs   ← starts everything silently, shows a small confirmation popup
stop-hidden.vbs    ← stops everything
```

Manage from the **Settings → ⚙️ Server** tab in the UI, or via CLI:
```bash
pm2 list              # see status
pm2 logs              # tail live logs
pm2 restart all       # restart both
pm2 stop all          # stop both
```

**Option B - start.bat (Windows, quick):**
```
start.bat
```
Checks if ports are free, launches backend + frontend in separate windows.

**Option C - Terminal windows (easier for development/debugging):**

Terminal 1 - Backend:
```bash
cd backend
venv\Scripts\activate          # Windows
# source venv/bin/activate    # macOS/Linux
python -m uvicorn app.main:app --host 0.0.0.0 --port 19000
```

Terminal 2 - Frontend:
```bash
cd frontend
npm run dev
```

### 6. Open

- **App:** http://localhost:3001
- **API docs:** http://localhost:19000/docs

First launch runs an onboarding wizard - the AI asks a few questions to set up your identity profile.

---

## Updating an Existing Install

If you already have DevForgeAI installed and just want the latest changes:

```bash
# 1. Pull latest code
git pull origin main

# 2. Update backend dependencies (always run this after a pull)
cd backend
venv\Scripts\activate        # Windows
# source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt

# 3. Update frontend dependencies (run this after a pull)
cd ../frontend
npm install

# 4. Restart
# If running via PM2 (background mode):
pm2 restart all

# If running in terminal windows: stop them (Ctrl+C) and start again
```

**What happens automatically on restart - you don't need to do these:**
- ✅ Database schema updates (new columns/tables added without losing data)
- ✅ Ollama model re-sync (any newly pulled models appear automatically)
- ✅ Default memory files created if missing

**What is never touched by a pull - your data is safe:**
- ✅ `backend/.env` - your API keys stay intact
- ✅ `data/` folder - images, snapshots, identity files, database all preserved
- ✅ `data/devforgeai.db` - your conversations, personas, agents stay untouched

**Common errors after a pull and how to fix them:**

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: No module named 'redis'` | New package added, pip not re-run | `pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'X'` | Any missing package | `pip install -r requirements.txt` |
| `Cannot find module '...'` (frontend) | New npm package added | `npm install` in `frontend/` |
| `address already in use :19000` | Old backend still running | Kill the old process then restart |
| `address already in use :3001` | Old frontend still running | Kill the old process then restart |
| Blank page or 404 in browser | Frontend not rebuilt | Stop and restart `npm run dev` |

> **Rule of thumb:** after every `git pull`, always run `pip install -r requirements.txt` and `npm install` before restarting. It's fast when nothing changed and prevents 99% of post-update errors.

---

## Features

### Chat
- OpenAI-compatible chat completions with streaming
- Automatic image generation intent detection - just say "generate an image of..."
- Multiple personas (each with its own model, system prompt, routing)
- Conversation history with pin, keep-forever, rename, export
- **Model override dropdown** - pick a specific model per-conversation (grouped by provider), independent of persona
- **Slash commands:** `/reset` `/image` `/persona` `/model` `/pin` `/export` `/theme` `/method` `/help`

### Agents
- 7 built-in types: Coder, Researcher, Designer, Reviewer, Planner, Executor, Writer
- Persona-based model resolution - persona prompt is the base, agent adds role-specific additions
- Custom tools, iteration limits, memory toggle
- Clicking a default agent opens it for editing; first save promotes it to a real DB record

### Image Generation
- **Provider choice** - Gemini Imagen (cloud) or ComfyUI (local) with auto-fallback
- **Workflow templates** - SDXL Standard, Flux Schnell (fast), Flux Dev (quality), SD 1.5 — or add your own
- **Checkpoint picker** - auto-discovers models from your ComfyUI install, filtered by workflow compatibility
- **Size & negative prompt** - per-workflow size presets, optional negative prompt
- **Model info on images** - shows which provider, checkpoint, and workflow was used
- Natural language intent detection - just say "generate an image of..."
- Gallery with lightbox, variations, edit-with-AI, download, delete
- Custom workflows: drop a `.json` file in `data/workflows/` and it appears automatically
- **Telegram delivery** - generated images are automatically sent to your Telegram chats
- Generate images directly from Telegram: `/image a golden retriever skiing`

### Session Snapshots & Memory
- Every chat exchange writes `data/context/YYYY-MM-DD/session_*.md`
- If a session is lost (crash, compaction, DB wipe), a recovery banner appears on reload
- Every 10 messages, key facts are distilled and appended to `data/context/MEMORY.md`
- Long-term memory accumulates across all conversations over time

### Learned Preferences
- Preferences detected automatically from chat every 10 messages (uses local Ollama model)
- Manual add, toggle on/off, delete from Settings → Preferences
- Categories: general, coding, communication, UI, workflow
- Active preferences injected into every chat context — the AI remembers what you like
- "Detect from Chat" button to manually scan recent conversations
- On-demand detection endpoint: `POST /v1/preferences/detect`

### Settings
- **Identity** - Edit SOUL.md, USER.md, IDENTITY.md; reset onboarding
- **API Keys** - Set/update/clear provider keys; hot-reloaded instantly (no restart needed)
- **Memory Files** - USER.md, CONTEXT.md, PREFERENCES.md injected into every chat
- **Preferences** - View, toggle, add, delete learned preferences; detect from chat
- **Image Generation** - Configure ComfyUI path, Python executable, URL, GPU devices, default provider/workflow
- **Conversations** - Browse and delete conversation history
- **Remote** - Telegram bot config, Tailscale setup
- **⚙️ Server** - Uptime, health checks, one-click backend restart

### Providers & Models
- On first startup: auto-discovers all locally installed Ollama models
- Only adds paid provider models (Anthropic, Google, OpenRouter, OpenAI) when API keys are set
- Add/update keys anytime in Settings → API Keys - models sync automatically
- Manual sync: `POST /v1/models/sync`

---

## Environment Variables

```env
# Database (auto-created, don't change unless you know why)
DATABASE_URL=sqlite+aiosqlite:///data/devforgeai.db

# AI Providers (at least one required)
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
OPENAI_API_KEY=

# Local AI
OLLAMA_BASE_URL=http://localhost:11434

# Image Generation (optional - falls back to Gemini)
COMFYUI_URL=http://localhost:8188

# App auth
MODELMESH_API_KEY=modelmesh_local_dev_key

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_IDS=

# Redis (optional - for multi-turn conversation memory)
# REDIS_URL=redis://localhost:6379
```

---

## Remote Access

DevForgeAI automatically works from any device on your network. The frontend detects the backend URL from the browser's hostname — no config needed.

### How it works

| You access from | Frontend auto-connects to |
|---|---|
| `http://localhost:3001` | `http://localhost:19000` |
| `http://192.168.1.50:3001` (LAN) | `http://192.168.1.50:19000` |
| `http://100.x.x.x:3001` (Tailscale) | `http://100.x.x.x:19000` |

Override: set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to hardcode a specific backend URL.

### Tailscale setup

If you use [Tailscale](https://tailscale.com) for remote access, add firewall rules (run as Administrator):

```powershell
# Windows - allow Tailscale subnet only
netsh advfirewall firewall add rule name="DevForgeAI API (19000)" dir=in action=allow protocol=tcp localport=19000 remoteip=100.64.0.0/10
netsh advfirewall firewall add rule name="DevForgeAI Frontend (3001)" dir=in action=allow protocol=tcp localport=3001 remoteip=100.64.0.0/10
```

### LAN access

For local network access without Tailscale, allow your LAN subnet:

```powershell
netsh advfirewall firewall add rule name="DevForgeAI API (LAN)" dir=in action=allow protocol=tcp localport=19000 remoteip=192.168.0.0/16
netsh advfirewall firewall add rule name="DevForgeAI Frontend (LAN)" dir=in action=allow protocol=tcp localport=3001 remoteip=192.168.0.0/16
```

Then access from any device on your network: `http://[server-IP]:3001`

---

## Project Structure

```
model_mesh/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, lifespan, router registration
│   │   ├── config.py            # Settings (reads .env)
│   │   ├── seed.py              # Default data + Ollama auto-sync on first run
│   │   ├── migrate.py           # Idempotent column migrations (runs on startup)
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── routes/              # API route handlers
│   │   │   ├── chat.py          # Chat completions + snapshot hooks + preference detection
│   │   │   ├── agents.py        # Agent CRUD + default agent recovery
│   │   │   ├── images.py        # Image generation, gallery, variations, ComfyUI workflows
│   │   │   ├── workflows.py     # Workflow template listing + ComfyUI checkpoint discovery
│   │   │   ├── preferences.py   # Learned preferences CRUD + LLM detection
│   │   │   ├── app_settings.py  # App-level settings (ComfyUI paths, defaults)
│   │   │   ├── model_sync.py    # Ollama + paid provider model sync
│   │   │   ├── api_keys.py      # API key management (hot-reload)
│   │   │   ├── context.py       # Snapshot recovery + MEMORY.md
│   │   │   ├── system.py        # Health, restart, snapshots
│   │   │   ├── telegram_bot.py  # Telegram polling bot + image delivery
│   │   │   ├── identity.py      # SOUL.md / USER.md / IDENTITY.md
│   │   │   └── ...
│   │   └── services/
│   │       ├── context_snapshot.py      # Snapshot writer + memory distillation
│   │       ├── memory_context.py        # Memory files + preferences injection
│   │       ├── app_settings_helper.py   # DB settings reader with env fallback
│   │       ├── ollama_sync.py           # Ollama model discovery
│   │       └── ...
│   ├── requirements.txt
│   └── .env                     # Your keys (never committed)
├── frontend/
│   └── src/app/
│       ├── chat/                # Chat UI + recovery banner
│       └── (main)/
│           ├── agents/          # Agent list + detail
│           ├── gallery/         # Image gallery
│           ├── settings/        # All settings tabs incl. Server
│           └── ...
└── data/                        # Auto-created, never committed
    ├── devforgeai.db            # SQLite database
    ├── soul.md                  # AI identity
    ├── user.md                  # Your profile
    ├── images/                  # Generated images
    ├── workflows/               # ComfyUI workflow templates (.json)
    └── context/                 # Session snapshots + MEMORY.md
```

---

## License

MIT
