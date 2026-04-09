# Frontend Component Inventory

## Reusable Components (`src/components/`)

| Component | File | Purpose | Props |
|-----------|------|---------|-------|
| `ModelFitnessCheck` | `ModelFitnessCheck.tsx` | VRAM compatibility check for Ollama models — shows fit/no-fit badge with GPU bar | `modelId: string`, `showGpuBar?: boolean`, `compact?: boolean` |
| `GpuStatusWidget` | `ModelFitnessCheck.tsx` | Dashboard GPU/VRAM status with utilization bar graphs | (self-contained, polls every 10s) |
| `PreferencesTab` | `PreferencesTab.tsx` | Learned preferences management — auto-detect from chat, manual add, toggle, filter by category | (none) |
| `ProjectSetupWizard` | `ProjectSetupWizard.tsx` | Multi-step project creation wizard (8 steps: intro, name, template, location, agents, sandbox, review, success) | `templates, onComplete, onDismiss` |
| `RunPanel` | `RunPanel.tsx` | Terminal-style panel for executing project commands with live SSE output stream | `projectId: string`, `compact?: boolean` |
| `ImageSettingsTab` | `ImageSettingsTab.tsx` | ComfyUI configuration (directory, python path, URL, GPU devices, default provider) | (none) |

## App-Level Components (`src/app/`)

| Component | File | Purpose |
|-----------|------|---------|
| `Navigation` | `Navigation.tsx` | Main sidebar — grouped nav items (MAIN/BUILD/CREATE/MANAGE), theme toggle, user menu, backend status indicator, collapsible |
| `NavigationWrapper` | `NavigationWrapper.tsx` | Conditional wrapper that hides sidebar on `/chat` routes |
| `ToastProvider` | `ToastProvider.tsx` | Global toast notification system + async task submission + notification polling (5s) |

## Page-Local Components (inline in page files)

### Chat Page (`chat/page.tsx` — 2256 lines)
| Component | Purpose |
|-----------|---------|
| `Sidebar` | Resizable conversation list with pinned/day grouping, persona/model selectors, search |
| `InlineImage` | Image display with lightbox, retry, metadata badges (provider/workflow/checkpoint) |
| `MessageBubble` | Chat message with markdown rendering, copy button, model badge, timestamp |
| `IdentityWizard` | Multi-mode setup wizard (first-run 8Q, soul 4Q, user 4Q, identity 3Q) — generates soul.md/user.md/identity.md |
| `renderMarkdown` | Local markdown renderer (duplicate of lib/markdown.ts) |

### Workbench Pages
| Component | File | Purpose |
|-----------|------|---------|
| `EventRow` | `workbench/[id]/page.tsx` | Single SSE event display (thought, tool call, file op) |
| `AgentCard` | `workbench/[id]/page.tsx` | Agent avatar, status, turns/files counters |
| `Turn` | `workbench/[id]/page.tsx` | Turn-based conversation view builder |
| `PhaseCard` | `workbench/pipelines/[id]/page.tsx` | Pipeline phase card with role avatar, status, artifacts |
| `ApprovalModal` | `workbench/pipelines/[id]/page.tsx` | Approve/reject/skip dialog with feedback input |
| `ArtifactViewer` | `workbench/pipelines/[id]/page.tsx` | JSON, Markdown, and Code viewer for phase outputs |

### Settings & Other
| Component | File | Purpose |
|-----------|------|---------|
| `ApiKeysTab` | `settings/page.tsx` | API key management with clear-impact analysis preview |
| `RemoteAccessTab` | `settings/remote.tsx` | Tailscale IP detection + Telegram bot status |
| `FileTree` | `projects/[id]/page.tsx` | Project file tree browser |
| `SandboxPanel` | `projects/[id]/sandbox.tsx` | Python venv, git snapshots/rollback, env vars management |
| `SessionCard` | `agents/sessions/page.tsx` | Agent session card with stats, auto-refresh |

## Component Categories

### Layout
- `Navigation`, `NavigationWrapper`, `(main)/layout.tsx`, `chat/layout.tsx`

### Form
- Persona create/edit forms, agent edit form, new project modal, settings tabs, identity wizard, login form

### Display
- `StatCard`, `StatusBadge`, `SessionCard`, `PhaseCard`, `ArtifactViewer`, `FileTree`, `GpuStatusWidget`, `ModelFitnessCheck`

### Navigation
- `Navigation` sidebar with grouped items, breadcrumbs in workbench

### Modal
- New session, approval review, lightbox, artifact viewer, new project wizard

### Feedback
- `ToastProvider`, local `Toast`, error boundaries, loading spinners (three orange bouncing dots)

## Design System Patterns

- **Colors**: Orange/amber primary (`bg-orange-500`), indigo secondary, gray scale for text/borders
- **Dark Mode**: Tailwind `class` strategy, full support via `dark:` prefixes
- **Cards**: `bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700`
- **Buttons**: Orange primary (`bg-orange-500 hover:bg-orange-600 text-white`), gray outlined secondary
- **Loading**: Three bouncing orange dots (consistent pattern)
- **Typography**: System font stack (`system-ui, -apple-system, sans-serif`), semibold headings
- **Shadows**: `shadow-sm` default, `shadow-md`/`shadow-lg` on hover
