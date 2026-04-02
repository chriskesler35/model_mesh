# DevForgeAI — Comprehensive Manual Test Plan

**Version:** 0.2.0
**Date:** 2026-04-02
**Tester:** ___________________________
**Environment:** ☐ Primary (G:\Model_Mesh) ☐ Secondary (Laptop) ☐ Remote (Tailscale)
**Browser:** ___________________________
**Backend URL:** http://localhost:19000
**Frontend URL:** http://localhost:3001

---

## How to Use This Document

1. Print this document (or open in a tablet)
2. Start DevForgeAI using `devforgeai_startup.bat`
3. Work through each section in order
4. Mark each test: ✅ Pass | ❌ Fail | ⏭️ Skipped | ⚠️ Partial
5. Write bug descriptions in the **Notes** column
6. When done, file bugs for all ❌ and ⚠️ items

---

## 1. APPLICATION STARTUP & HEALTH

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 1.1 | Backend starts | Run `start.bat` | Backend binds to port 19000, no errors in console | ☐ | |
| 1.2 | Frontend starts | Verify Next.js starts | Frontend accessible at localhost:3001 | ☐ | |
| 1.3 | Port conflict guard | Start with backend already running, run `start.bat` again | Should detect port in use and skip, not spawn duplicate | ☐ | |
| 1.4 | Health endpoint | GET http://localhost:19000/v1/health | Returns 200 with status "healthy" | ☐ | |
| 1.5 | Root endpoint | GET http://localhost:19000/ | Returns name: "DevForgeAI", version: "0.2.0" | ☐ | |
| 1.6 | Database auto-creation | Delete `data/devforgeai.db`, restart backend | DB recreated, tables seeded, no errors | ☐ | |
| 1.7 | Migration on startup | Start backend with existing DB | Migrations run (new columns added), no errors | ☐ | |
| 1.8 | Ollama model sync on startup | Start backend with Ollama running | Console shows model sync count | ☐ | |
| 1.9 | Backend health indicator (sidebar) | Open frontend, look at sidebar bottom | Green dot if backend healthy, red if not, pulses during check | ☐ | |
| 1.10 | Stop script | Run `stop.bat` | Both backend and frontend processes killed cleanly | ☐ | |

---

## 2. FIRST-RUN EXPERIENCE / IDENTITY WIZARD

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 2.1 | First-run detection | Clear identity files (`data/soul.md`, `data/user.md`, `data/identity.md`), open frontend | Onboarding wizard appears | ☐ | |
| 2.2 | Wizard step 1 — Name | Enter AI assistant name | Field accepts input, Next button enabled | ☐ | |
| 2.3 | Wizard step 2 — Personality | Choose personality traits | Options selectable, preview updates | ☐ | |
| 2.4 | Wizard step 3 — User info | Enter user name, preferences | Saved correctly | ☐ | |
| 2.5 | Wizard completion | Finish wizard | soul.md, user.md, identity.md created in data/ | ☐ | |
| 2.6 | Subsequent loads skip wizard | Reload page after wizard complete | Goes straight to dashboard, no wizard | ☐ | |
| 2.7 | Re-run via /onboard | Type `/onboard` in chat | Wizard re-opens | ☐ | |
| 2.8 | /soul command | Type `/soul` in chat | Opens soul.md editor | ☐ | |
| 2.9 | /identity command | Type `/identity` in chat | Opens identity editor | ☐ | |
| 2.10 | /user command | Type `/user` in chat | Opens user profile editor | ☐ | |

---

## 3. NAVIGATION & LAYOUT

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 3.1 | Sidebar renders | Open app | Left sidebar visible with all nav groups | ☐ | |
| 3.2 | Sidebar groups correct | Check sidebar | MAIN: Dashboard, Chat / BUILD: Agents, Sessions, Workbench, Projects / CREATE: Gallery, Methods / MANAGE: Collaborate, Personas, Models, Stats, Settings | ☐ | |
| 3.3 | Sidebar collapse | Click collapse button | Sidebar collapses to icons only | ☐ | |
| 3.4 | Collapse persists | Collapse sidebar, reload page | Still collapsed (localStorage) | ☐ | |
| 3.5 | Sidebar expand | Click expand button | Sidebar expands back to full | ☐ | |
| 3.6 | Active page highlight | Navigate to each page | Current page highlighted in sidebar | ☐ | |
| 3.7 | All nav links work | Click every sidebar link | Each page loads without error | ☐ | |
| 3.8 | Page title updates | Navigate to each page | Browser tab title changes | ☐ | |
| 3.9 | Mobile responsive | Resize window to < 768px | Layout adapts, no horizontal scroll, sidebar becomes hamburger/overlay | ☐ | |
| 3.10 | DevForgeAI branding | Check sidebar header | Shows "DevForgeAI" logo/text | ☐ | |

---

## 4. DASHBOARD

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 4.1 | Dashboard loads | Navigate to / | Dashboard renders with stat cards | ☐ | |
| 4.2 | Total requests card | Check dashboard | Shows total API requests count | ☐ | |
| 4.3 | Total tokens card | Check dashboard | Shows total tokens (input + output) | ☐ | |
| 4.4 | Total cost card | Check dashboard | Shows estimated total cost | ☐ | |
| 4.5 | Active models card | Check dashboard | Shows count of active models | ☐ | |
| 4.6 | Live stats refresh | Send a chat message, return to dashboard | Numbers increase | ☐ | |
| 4.7 | Dark mode toggle | Click theme toggle | Dashboard switches to dark mode, all cards readable | ☐ | |
| 4.8 | Dark mode persists | Toggle dark mode, reload | Still in dark mode | ☐ | |

---

## 5. CHAT

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 5.1 | Chat page loads | Navigate to /chat | Chat interface renders with input bar | ☐ | |
| 5.2 | Send message (Ollama) | Type message, press Enter/Send | Message sent, response streams back from local Ollama model | ☐ | |
| 5.3 | Send message (cloud) | Select cloud model, send message | Response returns from cloud provider | ☐ | |
| 5.4 | Message persistence | Send messages, reload page | Messages still visible | ☐ | |
| 5.5 | Conversation sidebar | Check left panel | Shows list of conversations | ☐ | |
| 5.6 | New conversation | Click "New" button | Creates fresh conversation, input clears | ☐ | |
| 5.7 | Switch conversations | Click different conversation in list | Chat loads that conversation's messages | ☐ | |
| 5.8 | Rename conversation | Click rename/edit on conversation | Name updates, persists on reload | ☐ | |
| 5.9 | Delete conversation | Click delete on conversation | Conversation removed from list and DB | ☐ | |
| 5.10 | Persona selector | Open persona dropdown | Shows all personas, can switch | ☐ | |
| 5.11 | Model override dropdown | Open model dropdown | Shows models grouped by provider, "persona default" option | ☐ | |
| 5.12 | Model override works | Select specific model, send message | Response uses selected model (check model_used in DB/response) | ☐ | |
| 5.13 | Token display | Send a message | Shows token count (in/out) on response | ☐ | |
| 5.14 | Cost display | Send a message | Shows estimated cost on response | ☐ | |
| 5.15 | Latency display | Send a message | Shows latency in ms | ☐ | |
| 5.16 | Long message rendering | Send/receive a very long message (1000+ words) | Scrolls properly, no overflow | ☐ | |
| 5.17 | Code block rendering | Receive a code response | Syntax highlighted, copy button works | ☐ | |
| 5.18 | Markdown rendering | Receive response with headers, lists, bold, etc. | Renders as formatted HTML | ☐ | |
| 5.19 | Error handling | Disconnect Ollama, send message | Graceful error message, not a crash | ☐ | |
| 5.20 | Auto-scroll | Receive streaming response | Chat scrolls to bottom automatically | ☐ | |
| 5.21 | Inline image display | Generate image via /image command | Image shows inline in chat | ☐ | |
| 5.22 | Image persistence | Generate image, reload page | Image still visible in chat | ☐ | |
| 5.23 | Memory context injection | Enable memory on persona, chat | Persona references memory context in response | ☐ | |
| 5.24 | Auto-router | Use persona with routing enabled | Different query types route to appropriate models | ☐ | |

---

## 6. SLASH COMMANDS

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 6.1 | Command palette opens | Type "/" in chat input | Floating command palette appears above input | ☐ | |
| 6.2 | Fuzzy search | Type "/on" | Shows /onboard as match | ☐ | |
| 6.3 | Keyboard nav | Press ↑↓ arrows | Highlights different commands | ☐ | |
| 6.4 | Enter selects | Highlight command, press Enter | Command executes | ☐ | |
| 6.5 | Esc dismisses | Press Escape | Palette closes | ☐ | |
| 6.6 | /reset | Execute /reset | Current conversation clears | ☐ | |
| 6.7 | /persona [name] | Execute /persona | Switches active persona | ☐ | |
| 6.8 | /model [name] | Execute /model | Shows model override options | ☐ | |
| 6.9 | /image [prompt] | Type /image a sunset | Image generation fires automatically (no double-submit) | ☐ | |
| 6.10 | /pin | Execute /pin | Conversation pinned | ☐ | |
| 6.11 | /export | Execute /export | Conversation exported as markdown file | ☐ | |
| 6.12 | /theme | Execute /theme | Dark/light mode toggles | ☐ | |
| 6.13 | /clear | Execute /clear | Chat display clears | ☐ | |
| 6.14 | /settings | Execute /settings | Navigates to settings page | ☐ | |
| 6.15 | /help | Execute /help | Shows all available commands | ☐ | |
| 6.16 | /method | Execute /method | Shows/switches development method | ☐ | |
| 6.17 | Command hints | Type /persona (with space) | Shows hint: `/persona <name>` | ☐ | |

---

## 7. IMAGE GENERATION & GALLERY

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 7.1 | Gallery page loads | Navigate to /gallery | Gallery renders, shows existing images (if any) | ☐ | |
| 7.2 | Image count displayed | Check gallery header | Shows total image count + refresh button | ☐ | |
| 7.3 | Generate via Gemini | Use image gen dialog with Gemini selected | Image generates, appears in gallery | ☐ | |
| 7.4 | Generate via ComfyUI | Use image gen dialog with ComfyUI selected | Image generates using selected workflow | ☐ | |
| 7.5 | Provider selector | Open gen dialog | Shows Gemini and ComfyUI options | ☐ | |
| 7.6 | Workflow dropdown (ComfyUI) | Select ComfyUI provider | Shows workflow list (SDXL, Flux Schnell, Flux Dev, SD 1.5) | ☐ | |
| 7.7 | Checkpoint dropdown | Select ComfyUI provider | Shows compatible checkpoints | ☐ | |
| 7.8 | Size selector | Open gen dialog | Size dropdown works | ☐ | |
| 7.9 | Negative prompt | Enter negative prompt | Applied to generation (ComfyUI) | ☐ | |
| 7.10 | ComfyUI status indicator | Check gen dialog | Shows green/red for ComfyUI connection | ☐ | |
| 7.11 | Lightbox | Click image in gallery | Opens full-size lightbox | ☐ | |
| 7.12 | Download button | Click download on image | Image downloads to local machine | ☐ | |
| 7.13 | Delete button | Click delete on image | Image removed from gallery after confirm | ☐ | |
| 7.14 | Generate variation | Click variation button on image | New variation generated from source image | ☐ | |
| 7.15 | Provider badge | Check image cards | Shows provider (Gemini/ComfyUI), checkpoint, workflow info | ☐ | |
| 7.16 | Image upload | Use upload button | Image uploaded and appears in gallery | ☐ | |
| 7.17 | Broken image fallback | (If applicable) | Image with error shows fallback/placeholder | ☐ | |
| 7.18 | Refresh button | Click refresh | Gallery reloads images | ☐ | |
| 7.19 | Error state | Disconnect ComfyUI, try generating | Shows error message with retry button | ☐ | |

---

## 8. MODELS PAGE

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 8.1 | Models page loads | Navigate to /models | Shows model list with provider status cards | ☐ | |
| 8.2 | Provider status cards | Check top section | Shows Ollama, Anthropic, Google, OpenRouter with status | ☐ | |
| 8.3 | Ollama sync button | Click sync | Discovers local Ollama models, adds new ones | ☐ | |
| 8.4 | Model list | Check model table | Shows all models with provider, name, pricing, context window | ☐ | |
| 8.5 | Add model manually | Click add, fill form | Model created in DB | ☐ | |
| 8.6 | Model lookup auto-fill | Add model, use lookup | Pricing and context window auto-fill | ☐ | |
| 8.7 | Edit model | Click edit on model | Form pre-fills, changes save | ☐ | |
| 8.8 | Delete model | Click delete | Model removed after confirm | ☐ | |
| 8.9 | Toggle active/inactive | Toggle model active switch | Model status changes, inactive models not used in chat | ☐ | |
| 8.10 | Filter by provider | Use provider filter | Shows only models from selected provider | ☐ | |

---

## 9. PERSONAS PAGE

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 9.1 | Personas page loads | Navigate to /personas | Shows persona list | ☐ | |
| 9.2 | Default persona exists | Check list | At least one default persona present | ☐ | |
| 9.3 | Create persona | Click new, fill form | Persona created with name, description, system prompt | ☐ | |
| 9.4 | Assign model | Create persona with primary model | Model assignment saved | ☐ | |
| 9.5 | Assign fallback model | Set fallback model | Fallback saved | ☐ | |
| 9.6 | Edit persona | Click edit | Form pre-fills, changes persist | ☐ | |
| 9.7 | Delete persona | Click delete (non-default) | Persona removed | ☐ | |
| 9.8 | Cannot delete default | Try deleting default persona | Prevented or shows warning | ☐ | |
| 9.9 | Memory toggle | Toggle memory on persona | Memory enabled/disabled, reflected in chat | ☐ | |
| 9.10 | Routing rules | Set routing rules (max_cost, prefer_local) | Rules saved and applied | ☐ | |
| 9.11 | Persona detail page | Click persona name | Detail page with full config | ☐ | |

---

## 10. AGENTS PAGE

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 10.1 | Agents page loads | Navigate to /agents | Shows 7 default agents | ☐ | |
| 10.2 | Default agents present | Check list | Coder, Researcher, Designer, Reviewer, Planner, Executor, Writer | ☐ | |
| 10.3 | Agent type icons | Check agent cards | Each type has distinct icon | ☐ | |
| 10.4 | Create agent | Click new, fill form | Agent created | ☐ | |
| 10.5 | Agent detail page | Click agent name | Full config view with system prompt, tools, model | ☐ | |
| 10.6 | Edit agent | Click edit on agent detail | Changes saved | ☐ | |
| 10.7 | Delete agent | Delete test agent | Removed from list | ☐ | |
| 10.8 | Persona-backed model | Assign persona to agent | Resolved model shows "via persona" | ☐ | |
| 10.9 | Direct model fallback | No persona, set model_id directly | Shows "direct" resolution | ☐ | |
| 10.10 | Agent Sessions tab | Navigate to /agents/sessions | Shows workbench sessions for agents | ☐ | |
| 10.11 | Session cards | Check session list | Shows token/cost stats, file counts | ☐ | |
| 10.12 | Click session → workbench | Click session card | Navigates to workbench detail | ☐ | |
| 10.13 | Delete session | Click delete on completed session | Session removed | ☐ | |

---

## 11. WORKBENCH (LIVE DEVELOPMENT)

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 11.1 | Workbench page loads | Navigate to /workbench | Shows session list | ☐ | |
| 11.2 | New session | Click new session | Session creation dialog with project, model, task | ☐ | |
| 11.3 | Model dropdown | Open model selector | Shows models grouped by provider | ☐ | |
| 11.4 | Start session | Fill form, start | Session begins, navigates to detail view | ☐ | |
| 11.5 | 3-panel layout | Check workbench detail | Left: file tree, Center: event stream, Right: file preview | ☐ | |
| 11.6 | File tree updates | Agent creates files | File tree updates in real-time | ☐ | |
| 11.7 | Event stream | Watch during agent work | Shows thoughts, tool calls, file ops, errors | ☐ | |
| 11.8 | File preview | Click file in tree | Shows file content with diff/preview | ☐ | |
| 11.9 | Intervention console | Type message during active session | Message sent to agent, appears in stream | ☐ | |
| 11.10 | Waiting for human | Agent encounters error | Orange highlight, agent pauses | ☐ | |
| 11.11 | Status badges | Watch during session | Shows: Thinking → Writing → Running → Done | ☐ | |
| 11.12 | Cancel session | Click cancel during active session | Session stops, status → cancelled | ☐ | |
| 11.13 | Session replay | Open completed session | Replays stored events smoothly (20ms delay) | ☐ | |
| 11.14 | Token tracking | Check completed session | Shows input/output tokens and estimated cost | ☐ | |
| 11.15 | SSE reconnection | Temporarily lose connection, reconnect | Stream reconnects or shows error gracefully | ☐ | |

---

## 12. PROJECTS

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 12.1 | Projects page loads | Navigate to /projects | Shows project list | ☐ | |
| 12.2 | Templates available | Click new project | Shows templates: blank, python-api, next-app, cli-tool | ☐ | |
| 12.3 | Create project (blank) | Create with blank template | Project created, directory exists | ☐ | |
| 12.4 | Create project (template) | Create with python-api template | Template files scaffolded | ☐ | |
| 12.5 | Custom path | Specify custom path during creation | Project created at specified location | ☐ | |
| 12.6 | Project detail page | Click project | Shows file tree and preview | ☐ | |
| 12.7 | File tree | Check project detail | Shows directory structure | ☐ | |
| 12.8 | File preview | Click file in tree | Shows file content | ☐ | |
| 12.9 | Open in Workbench | Click "Open in Workbench" | Navigates to workbench with project preloaded | ☐ | |
| 12.10 | Edit project | Rename project | Name persists | ☐ | |
| 12.11 | Delete project | Delete test project | Removed from list (check if files remain or deleted) | ☐ | |
| 12.12 | Auto-refresh after workbench | Complete a workbench session for project | File tree refreshes automatically | ☐ | |

---

## 13. SANDBOX (PROCESS ISOLATION)

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 13.1 | Sandbox tab visible | Open project detail | Sandbox tab present | ☐ | |
| 13.2 | Status cards | Check sandbox tab | Shows venv, git, env status | ☐ | |
| 13.3 | Create venv | Click "Create Virtual Env" | Python venv created in project dir | ☐ | |
| 13.4 | Install packages | Enter package name, install | Package installed in venv | ☐ | |
| 13.5 | Delete venv | Click delete venv | Venv directory removed | ☐ | |
| 13.6 | Git init | Click "Init Git" | Git repository initialized | ☐ | |
| 13.7 | Create snapshot | Click "Snapshot" | Git commit created as snapshot | ☐ | |
| 13.8 | Snapshot history | Check snapshot list | Shows previous snapshots with timestamps | ☐ | |
| 13.9 | Rollback | Select snapshot, rollback | Files restored to snapshot state (safety snapshot created first) | ☐ | |
| 13.10 | Env vars editor | Add environment variable | Saved to project .env file | ☐ | |
| 13.11 | Edit env vars | Modify existing var | Updated in .env | ☐ | |
| 13.12 | Delete env vars | Remove variable | Removed from .env | ☐ | |

---

## 14. METHODS (DEVELOPMENT METHODOLOGY)

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 14.1 | Methods page loads | Navigate to /methods | Shows 5 methods: Standard, BMAD, GSD, SuperPowers, GTrack | ☐ | |
| 14.2 | Activate method | Click activate on a method | Method becomes active, badge in chat | ☐ | |
| 14.3 | Method stacking | Add second method to stack | Both active, prompts concatenated | ☐ | |
| 14.4 | Conflict detection | Stack BMAD + GSD | Warning about conflict shown | ☐ | |
| 14.5 | Remove from stack | Remove a method | Removed from active stack | ☐ | |
| 14.6 | Clear stack | Clear all methods | Returns to Standard/none | ☐ | |
| 14.7 | Active method badge | Check chat header | Shows active method name | ☐ | |
| 14.8 | /method command | Type /method in chat | Shows/toggles methods | ☐ | |
| 14.9 | Method detail | Click method name | Shows full description and prompt | ☐ | |
| 14.10 | Prompt affects chat | Activate BMAD, send chat | System prompt includes method guidance | ☐ | |

---

## 15. COLLABORATION & MULTI-USER

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 15.1 | Collaborate page loads | Navigate to /collaborate | Shows tabs: Users, Workspaces, Handoffs, Audit Log | ☐ | |
| 15.2 | Create user | Add user with name, role | User created (owner/admin/member/viewer) | ☐ | |
| 15.3 | Edit user role | Change user role | Role updated | ☐ | |
| 15.4 | Delete user | Remove test user | User deleted | ☐ | |
| 15.5 | Create workspace | Create shared workspace | Workspace with members created | ☐ | |
| 15.6 | Add members to workspace | Add users to workspace | Members list updated | ☐ | |
| 15.7 | Edit workspace | Rename workspace | Name persists | ☐ | |
| 15.8 | Delete workspace | Remove test workspace | Workspace deleted | ☐ | |
| 15.9 | Create handoff | Initiate session handoff | Handoff created with from/to user | ☐ | |
| 15.10 | Accept handoff | Accept pending handoff | Status changes to accepted | ☐ | |
| 15.11 | Audit log | Perform several actions | All actions logged in audit trail | ☐ | |
| 15.12 | Audit log limit | Check log | Shows max 1000 events | ☐ | |

---

## 16. STATS PAGE

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 16.1 | Stats page loads | Navigate to /stats | Shows cost and usage summaries | ☐ | |
| 16.2 | Total cost | Check cost section | Shows total estimated cost | ☐ | |
| 16.3 | Cost by model | Check breakdown | Shows per-model cost | ☐ | |
| 16.4 | Cost by provider | Check breakdown | Shows per-provider cost | ☐ | |
| 16.5 | Token usage | Check usage section | Shows input/output tokens | ☐ | |
| 16.6 | Request count | Check usage section | Shows total requests | ☐ | |
| 16.7 | Success rate | Check usage section | Shows success rate percentage | ☐ | |
| 16.8 | Period filter | Change time period | Stats update for selected period | ☐ | |
| 16.9 | Workbench tokens included | Check after workbench session | Workbench token usage reflected in stats | ☐ | |

---

## 17. SETTINGS PAGE

### 17a. Identity Tab

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 17a.1 | Identity tab loads | Open Settings → Identity | Shows SOUL.md and USER.md editors | ☐ | |
| 17a.2 | Edit SOUL.md | Modify soul content, save | Saved to data/soul.md | ☐ | |
| 17a.3 | Edit USER.md | Modify user content, save | Saved to data/user.md | ☐ | |
| 17a.4 | Reset Onboarding | Click "Reset Onboarding" | Clears identity files, wizard re-appears | ☐ | |

### 17b. Memory Tab

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 17b.1 | Memory tab loads | Open Settings → Memory | Shows memory files list | ☐ | |
| 17b.2 | Reserved files filtered | Check list | identity.md NOT shown (reserved) | ☐ | |
| 17b.3 | Create memory file | Add new memory file | File created in data/ | ☐ | |
| 17b.4 | Edit memory file | Modify content, save | Changes persisted | ☐ | |
| 17b.5 | Delete memory file | Remove test file | File deleted | ☐ | |

### 17c. Preferences Tab

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 17c.1 | Preferences tab loads | Open Settings → Preferences | Shows preference list with categories | ☐ | |
| 17c.2 | Category filter | Select "coding" category | Shows only coding preferences | ☐ | |
| 17c.3 | Add preference manually | Fill form, add | New preference created | ☐ | |
| 17c.4 | Toggle preference | Toggle active switch | Preference enabled/disabled | ☐ | |
| 17c.5 | Delete preference | Click delete | Preference removed | ☐ | |
| 17c.6 | Detect from Chat | Click "Detect from Chat" | LLM analyzes recent chat, suggests preferences | ☐ | |
| 17c.7 | Passive detection | Send 10+ chat messages | Background detection fires, new preferences appear | ☐ | |

### 17d. Conversations Tab

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 17d.1 | Conversations tab loads | Open Settings → Conversations | Shows conversation list | ☐ | |
| 17d.2 | View conversation | Click conversation | Shows messages | ☐ | |
| 17d.3 | Delete conversation | Delete from settings | Removed from list | ☐ | |

### 17e. API Keys Tab

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 17e.1 | API Keys tab loads | Open Settings → API Keys | Shows provider key fields | ☐ | |
| 17e.2 | Set API key | Enter key for a provider | Key saved (masked display) | ☐ | |
| 17e.3 | Delete API key | Remove key | Key cleared | ☐ | |
| 17e.4 | Key not shown in plain text | Check display | Key masked (sk-***...) | ☐ | |
| 17e.5 | Telegram NOT in API Keys | Check list | Telegram config only in Remote tab | ☐ | |

### 17f. Remote Tab

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 17f.1 | Remote tab loads | Open Settings → Remote | Shows Tailscale, Telegram, Backend Control | ☐ | |
| 17f.2 | Tailscale status | Check section | Shows Tailscale IP and connection status | ☐ | |
| 17f.3 | Telegram bot setup | Enter bot token + chat IDs | Saved to .env, hot-reloaded | ☐ | |
| 17f.4 | Telegram test send | Click "Test Send" | Receives test message in Telegram | ☐ | |
| 17f.5 | Backend Control — status | Check section | Shows running/healthy/pid | ☐ | |
| 17f.6 | Backend Control — restart | Click restart | Backend restarts, reconnects | ☐ | |
| 17f.7 | Firewall rules shown | Check section | Shows required Tailscale firewall rules | ☐ | |

### 17g. Image Settings Tab

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 17g.1 | Image Settings tab loads | Open Settings → Image Settings | Shows ComfyUI configuration | ☐ | |
| 17g.2 | ComfyUI directory | Set ComfyUI dir path | Saved to app_settings | ☐ | |
| 17g.3 | ComfyUI Python path | Set Python executable path | Saved | ☐ | |
| 17g.4 | ComfyUI URL | Set ComfyUI server URL | Saved | ☐ | |
| 17g.5 | Default provider | Set default image provider | Applied to new generations | ☐ | |
| 17g.6 | ComfyUI status indicator | Check status | Shows green/red connection status | ☐ | |
| 17g.7 | Workflow overview cards | Check section | Shows available workflow templates | ☐ | |

---

## 18. TELEGRAM BOT

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 18.1 | Polling starts on boot | Start backend with valid bot token | Console shows Telegram polling started | ☐ | |
| 18.2 | /start command | Send /start to bot | Bot responds with welcome message | ☐ | |
| 18.3 | /help command | Send /help to bot | Bot shows available commands | ☐ | |
| 18.4 | /status command | Send /status to bot | Bot shows system status | ☐ | |
| 18.5 | /models command | Send /models to bot | Bot lists available models | ☐ | |
| 18.6 | Plain text chat | Send normal message | Bot responds via LLM | ☐ | |
| 18.7 | Conversation persistence | Chat multiple messages | Context maintained across messages | ☐ | |
| 18.8 | /sessions command | Send /sessions | Bot shows active sessions | ☐ | |
| 18.9 | /run command | Send /run coder task | Agent session starts | ☐ | |
| 18.10 | /cancel command | Send /cancel with session ID | Session cancelled | ☐ | |
| 18.11 | Chat ID filtering | Send from unauthorized chat | No response (filtered out) | ☐ | |
| 18.12 | Image forwarding | Generate image via /image | Image forwarded to Telegram | ☐ | |

---

## 19. REMOTE ACCESS (TAILSCALE)

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 19.1 | Frontend accessible | Open http://[tailscale-ip]:3001 from another device | Frontend loads | ☐ | |
| 19.2 | API accessible | curl http://[tailscale-ip]:19000/v1/health | Returns healthy | ☐ | |
| 19.3 | Chat works remotely | Send chat message from remote device | Response returns normally | ☐ | |
| 19.4 | Dynamic API_BASE | Open frontend on remote device | API calls go to correct IP (not localhost) | ☐ | |
| 19.5 | Gallery works remotely | View gallery from remote device | Images load correctly | ☐ | |
| 19.6 | Firewall rules | Without rules, try from Tailscale | Connection refused (expected) | ☐ | |
| 19.7 | With firewall rules | After adding rules, try from Tailscale | Connection works | ☐ | |

---

## 20. DARK MODE / THEMING

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 20.1 | Toggle works | Click dark mode toggle | Theme switches | ☐ | |
| 20.2 | Persists across reload | Toggle, reload | Same theme | ☐ | |
| 20.3 | All pages readable | Navigate all pages in dark mode | No invisible text, no broken contrast | ☐ | |
| 20.4 | Chat readable | Check chat in dark mode | Messages, code blocks, images all visible | ☐ | |
| 20.5 | Forms readable | Check forms in dark mode | Inputs, labels, buttons all visible | ☐ | |
| 20.6 | Gallery readable | Check gallery in dark mode | Images, badges, buttons all visible | ☐ | |
| 20.7 | Settings readable | Check all settings tabs in dark mode | No broken layout | ☐ | |
| 20.8 | /theme command | Use /theme slash command | Same as toggle | ☐ | |

---

## 21. ERROR HANDLING & EDGE CASES

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 21.1 | Backend down — frontend | Stop backend, use frontend | Shows error states, health dot red, no crash | ☐ | |
| 21.2 | Ollama down | Stop Ollama, send chat with Ollama model | Graceful error message | ☐ | |
| 21.3 | Invalid API key | Set wrong API key for cloud provider | Error returned to user, not a 500 | ☐ | |
| 21.4 | 404 page | Navigate to /nonexistent | Shows 404 page (not blank) | ☐ | |
| 21.5 | Empty states | Delete all conversations, check chat | Shows empty state message, not broken UI | ☐ | |
| 21.6 | Large file preview | Preview a 10MB file in project | Handles gracefully (truncate or error) | ☐ | |
| 21.7 | Special characters | Create persona named `<script>alert(1)</script>` | Sanitized, no XSS | ☐ | |
| 21.8 | Concurrent requests | Send 10 chat messages rapidly | No crashes, all get responses (possibly queued) | ☐ | |
| 21.9 | DB locked | Trigger multiple writes simultaneously | SQLite handles locking gracefully | ☐ | |
| 21.10 | Very long prompt | Send 10,000 character message | Handled (truncated to context window or error) | ☐ | |
| 21.11 | Unicode/emoji | Send messages with emoji 🎉 and CJK 你好 | Renders correctly in chat and DB | ☐ | |
| 21.12 | Rate limiting | Send >60 requests/min | Rate limit kicks in, returns 429 | ☐ | |
| 21.13 | CORS | Make API request from different origin | CORS headers present (allow_origins=*) | ☐ | |
| 21.14 | Conversation cleanup | Check auto-cleanup of 30-day-old conversations | Old conversations removed on startup | ☐ | |

---

## 22. PERFORMANCE

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 22.1 | Page load time | Load each page, measure | Each page loads in < 3 seconds | ☐ | |
| 22.2 | Chat response start | Send message, measure time to first token | First token in < 2s (local Ollama) | ☐ | |
| 22.3 | Gallery with many images | Load gallery with 50+ images | Loads without hanging | ☐ | |
| 22.4 | Conversation with many messages | Open conversation with 100+ messages | Scrolls smoothly | ☐ | |
| 22.5 | Workbench streaming | Watch live workbench session | Events stream without lag | ☐ | |
| 22.6 | Model list performance | Load models page with 40+ models | Renders quickly | ☐ | |
| 22.7 | Memory usage | Check browser memory during use | No memory leaks over 30 min | ☐ | |

---

## 23. DATA INTEGRITY

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 23.1 | Messages persist after restart | Send messages, restart backend | Messages still in DB | ☐ | |
| 23.2 | Workbench sessions persist | Create session, restart | Session still listed | ☐ | |
| 23.3 | Settings persist | Change settings, restart | Settings retained | ☐ | |
| 23.4 | Identity files persist | Edit soul.md, restart | Content preserved | ☐ | |
| 23.5 | API keys persist | Set key, restart | Key still set | ☐ | |
| 23.6 | Projects persist | Create project, restart | Project still listed, files intact | ☐ | |
| 23.7 | Preferences persist | Add preference, restart | Preference still active | ☐ | |
| 23.8 | Conversation rename persists | Rename conversation, reload | Name preserved | ☐ | |

---

## 24. HELP PAGE

| # | Test | Steps | Expected Result | Status | Notes |
|---|------|-------|-----------------|--------|-------|
| 24.1 | Help page loads | Navigate to /help | Help content renders | ☐ | |
| 24.2 | Content useful | Read help page | Covers main features and usage | ☐ | |

---

## BUG LOG

| # | Section | Test # | Description | Severity | Screenshot |
|---|---------|--------|-------------|----------|------------|
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |

---

## SIGN-OFF

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Tester | | | |
| Developer | | | |

---

**Total Tests:** ~250
**Estimated Time:** 4-6 hours for complete manual pass
