# Frontend Architecture

Next.js 14 web frontend for DevForgeAI.

## Stack

- Next.js 14.1.0
- React 18
- TypeScript 5.3
- Tailwind CSS 3.4
- Dark mode via class strategy

## Architecture Pattern

App Router with route groups, client-side state, SSE real-time.

## Route Structure

### (main) Group

Uses sidebar navigation. Includes:
- Dashboard
- Agents
- Collaborate
- Conversations
- Gallery
- Help
- Methods
- Models
- Personas
- Projects
- Settings
- Stats
- Workbench

### Standalone Routes

| Route | Purpose |
|-------|---------|
| `/chat` | Full-screen chat interface |
| `/login` | Authentication page |
| `/share/[token]` | Shared conversation view |
| `/auth/github/callback` | GitHub OAuth callback |
| `/auth/openrouter/callback` | OpenRouter OAuth callback |

## Key Pages

| Page | Description |
|------|-------------|
| `/chat` (2256 lines) | Full chat with resizable sidebar, SSE streaming, identity wizard, inline images, markdown renderer |
| `/workbench/[id]` | Single-agent sessions with SSE events, turn-based conversation, RunPanel |
| `/workbench/pipelines/[id]` | Multi-agent swim-lane UI with approval gates |
| `/gallery` | Image grid with lightbox, ComfyUI generation, variation creation |
| `/projects/[id]` | File browser, sandbox panel with venv/git/env management |
| `/settings` | API keys (with clear impact preview), preferences, image settings, remote access, backend control |

## State Management

No Redux or Zustand. All local `useState`.

- **localStorage**: Theme, auth token, user, sidebar state
- **sessionStorage**: OAuth flows

## API Layer

| Module | Purpose |
|--------|---------|
| `lib/config.ts` | Dynamic API base from `window.location`, Proxy-based `AUTH_HEADERS` |
| `lib/api.ts` | `ApiClient` singleton with typed methods |
| `lib/types.ts` | TypeScript interfaces |
| `lib/markdown.ts` | Lightweight custom renderer (no external dependencies) |
| `lib/openrouter-oauth.ts` | PKCE OAuth helpers |
| `app/api/` | Next.js routes for backend proxy (health, start/stop, README) |

## Real-time Communication

**SSE (Server-Sent Events)** for:
- Chat streaming
- Workbench events
- Pipeline updates
- Project runner output

**Polling intervals**:
| Target | Interval |
|--------|----------|
| Notifications | 5s |
| Backend health | 15s |
| Agent sessions | 3s (active) / 15s (idle) |
| GPU status | 10s |

## Design System

- **Primary accent**: Orange/amber
- **Secondary accent**: Indigo
- **Card style**: `rounded-xl`
- **Theme**: Dark mode throughout
- **Font**: System font stack
- **Loading indicator**: Three-dot orange spinner
