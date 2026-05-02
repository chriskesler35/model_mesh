# Days 31-60: Skills & Tools Marketplace — Context & Decisions

> Phase 5, 6, 7 (3-phase delivery)
> Decision Date: 2026-04-21
> Scope: Full marketplace with discovery, install, and management

## 1. Discovery Decisions

### Scope: Full 3-Phase Delivery
- **Phase 5 (Discovery)**: Marketplace page with search, filters, skill cards
- **Phase 6 (Install)**: Guided install flow with progress and rollback handling
- **Phase 7 (Manager)**: Enable/disable/update/remove/health checks for installed skills
- **Rationale**: Users expect complete workflow from discovery to management, not staggered features

### Implementation Order: Frontend-First
- **Phase 5**: Build marketplace UI with mocked API responses (no backend blocking)
- **Phases 6-7**: Wire real backend endpoints as frontend UI solidifies
- **Rationale**: Faster visual validation, clearer API contract from UX perspective

### Data Source: Curated Local Catalog
- **Phase 5**: `backend/skills_catalog.json` with hand-curated 20-30 skills/tools
- **Seed data**: Include BMAD, GSD, Superpowers, popular open-source tools (Langchain, DSPy, Ollama, etc.)
- **Metadata per skill**: name, description, use_cases[], languages[], complexity, trust_level, compatibility, install_url, manifest_url
- **Future path**: GitHub/Hugging Face connectors extend catalog automatically
- **Rationale**: Reduces external API setup friction, easier iteration on search/filter UX

## 2. Skill Manifest Standard (Phase 6 Prerequisite)

```json
{
  "manifest_version": "1.0",
  "skill_id": "langchain-core",
  "name": "LangChain Core",
  "version": "0.1.0",
  "purpose": "Chains and agents for LLM applications",
  "runtime_requirements": {
    "python": ">=3.8",
    "memory_mb": 512,
    "disk_mb": 100
  },
  "install_steps": [
    { "type": "pip_install", "package": "langchain", "version": "^0.1.0" },
    { "type": "health_check", "command": "python -c 'import langchain; print(langchain.__version__)'" }
  ],
  "required_permissions": ["internet", "file_write"],
  "compatibility": {
    "os": ["windows", "linux", "macos"],
    "architectures": ["x86_64", "arm64"]
  }
}
```

## 3. UI Layout: Marketplace Page

**Route**: `/marketplace` (new top-level page)

**Layout**:
- **Top**: Search bar + "Advanced Filters" dropdown
- **Filters sidebar** (collapsible): Use Case, Language, Complexity, Trust Level, Compatibility Status
- **Main grid**: Skill cards (3 columns) with:
  - Icon/avatar
  - Name + short description
  - Use cases (chips)
  - Language badges
  - Complexity indicator
  - Install button (or "Installed" badge if already present)
- **Right panel** (on card click): Full details, manifest preview, install CTA

## 4. Mocked API Responses (Phase 5)

**Endpoint**: `POST /v1/marketplace/search`
- Request: `{ search_query, filters: { use_cases, languages, complexity, trust_level } }`
- Response: Filtered skills from `skills_catalog.json` (mocked in-memory, no DB yet)
- Status: 200 with results array

**Endpoint**: `GET /v1/marketplace/skill/:skill_id`
- Response: Full skill metadata + manifest preview

## 5. Install Flow: Mocked (Phase 6)

**Endpoint**: `POST /v1/skills/install`
- Request: `{ skill_id, options: {...} }`
- Response: Install job ID + stream URL for progress
- **Mocked behavior**: Simulate 5-step install (download, validate, extract, health_check, finalize) over ~10 seconds
- **Success path**: All steps 100%, skill added to installed list
- **Failure path**: Step 3 fails (mock error), then rollback prompts user to retry or remove

## 6. Installed Skills Manager (Phase 7)

**Frontend**: New page `/skills/installed` showing:
- List of installed skills with version, install date, health status
- Enable/disable toggles
- Update button (if newer version available)
- Remove button (with confirm dialog)
- Health status indicator (green=healthy, yellow=degraded, red=failed)

**Mocked endpoints**:
- `GET /v1/skills/installed` → returns list
- `POST /v1/skills/:skill_id/toggle` → toggles enable/disable
- `POST /v1/skills/:skill_id/remove` → removes (mocked)
- `GET /v1/skills/:skill_id/health` → returns mock health status

## 7. Storage: Where Data Lives (Phase 5)

- **skills_catalog.json**: Backend static asset, pre-seeded with 20-30 curated skills
- **installed_skills**: Frontend local storage for Phase 5 (in-memory state)
- **Phase 6+**: Backend persistence table `installed_skills` (alembic migration)

## 8. Next Steps

- **Phase 5 planning**: Scope UI components, mock API routes, seed catalog content
- **Phase 6 planning**: Install orchestrator, progress streaming, rollback logic
- **Phase 7 planning**: Manager CRUD, health check polling

---

**Locked Decisions**: 
- ✅ Full 3-phase (not MVP)
- ✅ Frontend-first (mocked APIs)
- ✅ Curated catalog (JSON, not live APIs yet)
- ✅ Manifest standard (schema locked above)
