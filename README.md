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
| Ports | Backend: 19001 preferred locally, 19000 fallback/Docker · Frontend: 3001 |

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
python -m uvicorn app.main:app --host 0.0.0.0 --port 19001
```

Terminal 2 - Frontend:
```bash
cd frontend
npm run dev
```

### 6. Open

- **App:** http://localhost:3001
- **API docs:** http://localhost:19001/docs

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
| `address already in use :19001` | Old backend still running | Kill the old process then restart |
| `address already in use :3001` | Old frontend still running | Kill the old process then restart |
| Blank page or 404 in browser | Stale webpack cache | Restart `npm run dev` (cache auto-clears on start) |

> **Self-healing:** The frontend automatically clears stale caches on startup. If a page crashes at runtime, error boundaries catch it and attempt auto-recovery before showing a manual retry UI — you should never see a blank white page.

> **Rule of thumb:** after every `git pull`, always run `pip install -r requirements.txt` and `npm install` before restarting. It's fast when nothing changed and prevents 99% of post-update errors.

---

## Features

### Chat
- OpenAI-compatible chat completions with streaming
- Automatic image generation intent detection - just say "generate an image of..."
- **Inline image preview** - generated images appear directly in chat with loading states; click to open a full-size lightbox with download
- Multiple personas (each with its own model, system prompt, routing)
- Conversation history with pin, keep-forever, rename, export — sessions persist immediately on first message
- **Model override dropdown** - pick a specific model per-conversation (grouped by provider), independent of persona
- **Slash commands:** `/reset` `/image` `/persona` `/model` `/pin` `/export` `/theme` `/method` `/help`

### Agents
- 7 built-in types: Coder, Researcher, Designer, Reviewer, Planner, Executor, Writer
- Persona-based model resolution - persona prompt is the base, agent adds role-specific additions
- Custom tools, iteration limits, memory toggle
- Clicking a default agent opens it for editing; first save promotes it to a real DB record

### Image Generation
- **Provider choice** - Gemini Imagen (cloud) or ComfyUI (local) with auto-fallback
- **Workflow templates** - SDXL Standard, Flux Schnell (fast), Flux Dev (quality), Flux Uncensored + LoRA, SD 1.5 — or add your own
- **Checkpoint picker** - auto-discovers models from your ComfyUI install, filtered by workflow compatibility
- **LoRA support** - auto-discovers LoRA models from ComfyUI, with strength slider; dynamically injected into any workflow
- **Size & negative prompt** - per-workflow size presets, optional negative prompt
- **Editor workflow conversion** - ComfyUI editor-format workflows auto-converted to API format at generation time
- **Model info on images** - shows which provider, checkpoint, and workflow was used
- Natural language intent detection - just say "generate an image of..."
- Gallery with lightbox, variations, edit-with-AI, download, delete
- Custom workflows: drop a `.json` file in `data/workflows/` and it appears automatically
- Workflows also discovered from your ComfyUI `workflows/` and `user/default/workflows/` directories
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
  - **Auto-sync**: Adding a provider key instantly syncs that provider's models into your Models list — no manual action needed
  - **OpenRouter OAuth**: Click "Connect with OAuth" to authorize via PKCE flow (no copy/paste)
  - **Safe key removal**: Clearing a key shows an impact report with all affected personas/agents and lets you reassign them to replacement models before the key is cleared
- **Memory Files** - USER.md, CONTEXT.md, PREFERENCES.md injected into every chat
- **Preferences** - View, toggle, add, delete learned preferences; detect from chat
- **Image Generation** - Configure ComfyUI path, Python executable, URL, GPU devices, default provider/workflow
- **Conversations** - Browse and delete conversation history
- **Remote** - Telegram bot config, Tailscale setup
- **⚙️ Server** - Uptime, health checks, one-click backend restart

### Providers & Models
- On first startup: auto-discovers all locally installed Ollama models
- Only adds paid provider models (Anthropic, Google, OpenRouter, OpenAI) when API keys are set
- Add/update keys anytime in Settings → API Keys — models sync automatically
- **Remove a key**: affected personas and agents get a replacement picker before the key is cleared (no orphaned references)
- Manual sync: `POST /v1/models/sync`

### Projects
- **Guided Setup Wizard**: 6-step hybrid wizard walks new users through project creation
  - Naming + description → template picker → location → agent assignment → sandbox mode → review
  - Visual pickers for templates/agents/sandbox, conversational prompts for free-text fields
  - "I'll finish manually" escape hatch on every step
- **Quick Create**: traditional one-screen modal for power users
- 4 built-in templates: Blank, Python API (FastAPI), Next.js App, CLI Tool
- Sandbox modes: Restricted (project-dir-only, blocks shell) or Full Access
- Point agents at any directory on disk — projects can register existing folders or scaffold new ones

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

## ComfyUI Setup & Configuration

DevForgeAI can use [ComfyUI](https://github.com/comfyanonymous/ComfyUI) for local image generation. This section covers installation, GPU tuning, and workflow setup.

### Prerequisites

- **ComfyUI** installed somewhere on your machine (e.g. `E:\AI_Models\ComfyUI`)
- **Python 3.11** with PyTorch + CUDA (ComfyUI's requirement)
- At least one NVIDIA GPU with 8+ GB VRAM (12 GB recommended for Flux models)

### Connecting DevForgeAI to ComfyUI

1. Go to **Settings > Image Generation** in the DevForgeAI UI
2. Set **ComfyUI Directory** to your ComfyUI install path (e.g. `E:\AI_Models\ComfyUI`)
3. Set **Python Executable** to the Python that has PyTorch installed (e.g. `C:\...\Python311\python.exe`)
4. Set **ComfyUI URL** to `http://localhost:8188` (default)
5. Set **GPU Devices** to your preferred CUDA device order (e.g. `1,0` for dual-GPU with GPU 1 primary)
6. Set **Default Image Provider** to `ComfyUI (Local)` if you want local generation by default

DevForgeAI will auto-launch ComfyUI when needed and auto-discover your checkpoints, LoRAs, and workflows.

### GPU Configuration

ComfyUI's launch flags control how it uses your GPU(s). The right settings depend on your hardware.

#### Single GPU

| VRAM | Recommended flags | Notes |
|------|-------------------|-------|
| 24 GB (4090, 3090) | `--gpu-only --cuda-malloc --fast` | Everything stays on GPU, fastest |
| 12 GB (3060, 4070) | `--highvram --cuda-malloc --fast` | Keeps models in VRAM, offloads only when necessary |
| 8 GB (3070, 4060) | `--cuda-malloc --fast` | Default VRAM management, good balance |
| 6 GB or less | `--lowvram --cuda-malloc` | Aggressive offloading to fit in limited VRAM |

#### Dual GPU

For dual-GPU setups, use `CUDA_VISIBLE_DEVICES` to control GPU priority:

```bash
# GPU 1 primary, GPU 0 as overflow
set "CUDA_VISIBLE_DEVICES=1,0"

# GPU 0 primary, GPU 1 as overflow
set "CUDA_VISIBLE_DEVICES=0,1"
```

Recommended flags for dual-GPU:
```
--highvram --async-offload 2 --cuda-malloc --fast
```

- **`--highvram`** keeps models in VRAM as long as possible
- **`--async-offload 2`** enables asynchronous weight transfer between GPUs (overlaps compute with data movement)
- Do NOT use `--gpu-only` with 12 GB cards running Flux models (they need ~13 GB for UNET + CLIP + VAE + LoRA)
- Do NOT use `--cuda-device` — it hides other GPUs. Use `CUDA_VISIBLE_DEVICES` instead

#### Example Launcher Script (Windows)

Create a `.bat` file for consistent startup:

```batch
@echo off
title ComfyUI Launcher

:: Kill any existing ComfyUI on port 8188
for /f "tokens=5" %%p in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":8188 "') do (
    taskkill /PID %%p /F >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:: GPU order: physical GPU 1 becomes cuda:0 (primary)
set "CUDA_VISIBLE_DEVICES=1,0"

:: Performance environment variables
set "NVIDIA_TF32_OVERRIDE=1"
set "CUDA_MODULE_LOADING=LAZY"
set "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True"

cd /d "E:\AI_Models\ComfyUI"
"C:\...\python.exe" main.py ^
    --listen 0.0.0.0 ^
    --port 8188 ^
    --highvram ^
    --async-offload 2 ^
    --cuda-malloc ^
    --fast ^
    --preview-method auto ^
    --enable-cors-header "*"
```

Adjust paths and GPU flags to match your setup.

### Workflows

DevForgeAI discovers workflow templates from three locations (in priority order):

1. **`data/workflows/`** — built-in templates (SDXL Standard, Flux Dev, Flux Schnell, SD 1.5)
2. **`{ComfyUI}/workflows/`** — your main ComfyUI workflows folder
3. **`{ComfyUI}/user/default/workflows/`** — ComfyUI's per-user workflows

#### Built-in Workflow Templates

Templates use `{{placeholder}}` variables that get replaced with your UI selections:

| Placeholder | Replaced with |
|-------------|---------------|
| `{{prompt}}` | Your text prompt |
| `{{negative_prompt}}` | Negative prompt |
| `{{checkpoint}}` | Selected checkpoint model |
| `{{width}}` / `{{height}}` | Image dimensions |
| `{{lora_name}}` | Selected LoRA model |
| `{{lora_strength}}` | LoRA strength slider value |

#### Creating Custom Workflow Templates

Place a `.json` file in `data/workflows/` with this structure:

```json
{
  "name": "My Custom Workflow",
  "description": "Description shown in the UI",
  "category": "txt2img",
  "default_checkpoint": "myModel.safetensors",
  "compatible_checkpoints": ["myModel.safetensors", "otherModel.safetensors"],
  "default_size": "1024x1024",
  "sizes": ["1024x1024", "768x1024", "1024x768"],
  "workflow": {
    "4": {
      "class_type": "CheckpointLoaderSimple",
      "inputs": { "ckpt_name": "{{checkpoint}}" }
    },
    "6": {
      "class_type": "CLIPTextEncode",
      "inputs": { "clip": ["4", 1], "text": "{{prompt}}" }
    }
  }
}
```

The `workflow` key must contain the ComfyUI **API format** (node-ID keys with `class_type` and `inputs`), not the editor format.

#### Using ComfyUI Editor Workflows Directly

Workflows saved from the ComfyUI editor (with `nodes` and `links` arrays) are **automatically converted** to API format at generation time. They'll work, but since they don't have `{{placeholder}}` variables, the checkpoint/LoRA names are hardcoded to whatever was set when you saved the workflow in ComfyUI.

For full control over checkpoint/LoRA selection from the DevForgeAI UI, create a template with placeholders.

#### LoRA Support

When using ComfyUI, the image generation panel shows a LoRA dropdown (auto-populated from your ComfyUI `models/loras/` folder) and a strength slider. If the selected workflow doesn't already include a `LoraLoader` node, one is dynamically injected and wired into the model/clip chain.

### Troubleshooting ComfyUI

| Symptom | Cause | Fix |
|---------|-------|-----|
| "ComfyUI not reachable" | ComfyUI not running or wrong URL | Start ComfyUI, check URL in Settings |
| Always falls back to Gemini | ComfyUI errors are caught and Gemini is used as fallback | Check `logs/backend-error.log` for the real ComfyUI error |
| "prompt_no_outputs" | Workflow has no SaveImage node | Ensure workflow includes a SaveImage or PreviewImage node |
| "prompt_outputs_failed_validation" | Invalid checkpoint/sampler name | Check that the checkpoint file exists in ComfyUI's models folder |
| Generation times out | Model loading + generation exceeds timeout | Normal for first gen (model loads into VRAM); timeout is 10 minutes |
| OOM (Out of Memory) | Model too large for VRAM | Use `--highvram` instead of `--gpu-only`, or use FP8 model variants |
| Models offloading to RAM | ComfyUI launched without VRAM flags | Use `--highvram` flag; check DevForgeAI isn't auto-launching with defaults |
| Images all look the same | Workflow/checkpoint selection not reaching ComfyUI | Restart backend to pick up latest code; check dropdown selections |
| UTF-8 BOM errors on workflows | Workflow JSON saved with BOM encoding | Handled automatically (uses `utf-8-sig` decoding) |

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
│       ├── chat/                # Chat UI + inline images + error boundary
│       ├── api/health/          # Frontend health + self-healing endpoint
│       ├── api/backend/         # Backend process control (start/stop/restart)
│       ├── global-error.tsx     # App-wide error boundary with auto-recovery
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
