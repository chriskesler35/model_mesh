# Phase 5 Plan: Marketplace Discovery UI + Mocked Search

> Target: Full-featured marketplace page (search, filters, skill cards)
> Approach: Frontend-first with mocked API responses
> Commits: 1 per task, or 1 per major component

## Phase Goal
Enable users to **discover skills and tools** through search and filtering without needing to navigate external platforms.

## Acceptance Criteria
- ✅ Users can search skills by name or description
- ✅ Users can filter by use case, language, complexity, trust level
- ✅ Skill cards display: name, description, use cases, languages, complexity, trust badge, install button
- ✅ Clicking a card shows full details and manifest preview
- ✅ "Installed" badge appears on already-installed skills
- ✅ Search/filter results update instantly (no page reload)
- ✅ Marketplace is accessible from main navigation

## Work Breakdown

### Task 1: Create Curated Skills Catalog
**Scope**: `backend/skills_catalog.json` with 20-30 pre-seeded skills
**What to include**:
- BMAD (core method)
- GSD (core method)
- Superpowers (core method)
- Popular open-source: Langchain, DSPy, Ollama, Hugging Face Transformers, Llamaindex
- Common tools: Git integration, Docker, VS Code extensions
- AI/ML tools: AutoGen, CrewAI, Semantic Kernel

**Data structure per skill**:
```json
{
  "skill_id": "langchain-core",
  "name": "LangChain Core",
  "description": "Build applications with LLMs through composable abstractions",
  "use_cases": ["llm-chains", "agents", "rag", "structured-output"],
  "languages": ["python"],
  "complexity": "intermediate",
  "trust_level": "verified",  // verified, community, experimental
  "version": "0.1.0",
  "install_url": "https://github.com/langchain-ai/langchain",
  "manifest_url": "https://raw.githubusercontent.com/.../manifest.json",
  "icon_url": "https://example.com/langchain.png"
}
```

**Deliverable**: `backend/skills_catalog.json` loaded in memory on startup

**Commit**: "feat(marketplace): add curated skills catalog (20+ skills)"

---

### Task 2: Create Marketplace Backend Routes (Mocked)
**Scope**: Mocked API endpoints for Phase 5 (real backend comes in Phase 6+)

**Routes**:
```python
# GET /v1/marketplace/skills
# Query params: ?search=<query>&use_cases=<comma-sep>&languages=<comma-sep>&complexity=<level>&trust_level=<level>
# Returns: filtered skills from catalog

# GET /v1/marketplace/skill/<skill_id>
# Returns: Full skill details + manifest metadata

# GET /v1/marketplace/filters
# Returns: { use_cases: [], languages: [], complexity_levels: [], trust_levels: [] }
# (helps frontend populate filter options)
```

**Implementation**:
- Load `skills_catalog.json` on app startup → `g.skills_catalog`
- Filter in-memory based on query and filter params
- Return JSON response

**Deliverable**: 3 endpoints in `backend/app/routes/marketplace.py`

**Commit**: "feat(marketplace): add mocked search and filter endpoints"

---

### Task 3: Create Marketplace Frontend Page
**Scope**: `frontend/src/app/(main)/marketplace/page.tsx`

**Layout**:
- **Header**: "Skills & Tools Marketplace" title + search bar
- **Filters sidebar** (left, collapsible on mobile):
  - Search input (live search)
  - Use Case (multi-select checkboxes)
  - Language (multi-select checkboxes)
  - Complexity (radio buttons: beginner, intermediate, advanced)
  - Trust Level (radio buttons: verified, community, experimental)
  - "Clear Filters" button
- **Main grid** (right): 3-column grid of skill cards
- **Skill card**: Icon, name, short description, use cases (chip badges), language badges, complexity badge, "Install" button
- **Card modal** (on click): Full details pane with manifest preview and install CTA

**State**:
- `skills`: fetched from API
- `searchQuery`: text input
- `filters`: { use_cases: [], languages: [], complexity: null, trust_level: null }
- `selectedSkill`: for detail view
- `installedSkills`: list of already-installed (fetched from `/v1/skills/installed`)

**Effects**:
- On mount: Fetch skill catalog, fetch installed skills list
- On filter/search change: Fetch filtered results (debounced)

**Deliverable**: Marketplace page with live search/filter UI

**Commit**: "feat(marketplace): create marketplace discovery page with search and filters"

---

### Task 4: Create Skill Card Components
**Scope**: Reusable UI components for marketplace

**Components**:
- `SkillCard.tsx`: Display single skill (name, desc, use cases, languages, complexity, install btn)
- `SkillDetailPane.tsx`: Expanded view with manifest preview and install CTA
- `FilterPanel.tsx`: Sidebar with all filter options

**Deliverable**: 3 new components in `frontend/src/components/marketplace/`

**Commit**: "feat(marketplace): create skill card and filter panel components"

---

### Task 5: Wire Marketplace into Navigation
**Scope**: Add "Marketplace" link to main navigation + create route

**Changes**:
- Update `frontend/src/app/(main)/layout.tsx` or navigation component to add Marketplace link
- Ensure `/marketplace` route is accessible
- Add breadcrumb or navigation indicator

**Deliverable**: Marketplace accessible from main nav

**Commit**: "feat(marketplace): add marketplace link to main navigation"

---

### Task 6: Wire "Install" Button (Phase 5 Version)
**Scope**: Install button redirects/shows phase 6 note

**Behavior**:
- Click "Install" → Show toast or modal: "Install flow coming in Phase 6. For now, you can browse and favorite skills."
- Or: Disable install button with tooltip "Available in Phase 6"

**Deliverable**: UX clarity that Phase 5 is discovery-only

**Commit**: "feat(marketplace): add phase 5 install button placeholder"

---

### Task 7: Add Mock "Installed Skills" Endpoint
**Scope**: Mock `GET /v1/skills/installed` for Phase 5

**Response**: Empty list for Phase 5 (no install logic yet)

**Deliverable**: Frontend can fetch installed list (will be real in Phase 6)

**Commit**: "feat(marketplace): add installed skills mock endpoint"

---

## Technical Decisions Locked

1. **Mocking approach**: All data in-memory from `skills_catalog.json`, no database queries yet
2. **Search strategy**: Simple substring match on name + description; exact match on tags
3. **Filter strategy**: Multi-select for use_cases/languages (OR logic); single-select for complexity/trust (exact match)
4. **Persistence**: Installed skills stored in Phase 6 (Phase 5 uses mock empty list)
5. **UI framework**: Tailwind + shadcn/ui (consistent with existing Workbench)

## Success Verification

- ✅ Navigate to `/marketplace` → page loads with 20+ skills
- ✅ Search for "langchain" → results update instantly
- ✅ Filter by "intermediate" complexity → shows only intermediate skills
- ✅ Click a skill card → detail pane opens with manifest info
- ✅ Install button shows phase 6 placeholder message
- ✅ No TypeScript/linting errors on new files
- ✅ Marketplace link visible in main navigation

## Effort Estimate

- Task 1 (Catalog): 30 min
- Task 2 (Backend routes): 20 min
- Task 3 (Frontend page): 60 min
- Task 4 (Components): 40 min
- Task 5 (Navigation): 10 min
- Task 6 (Install placeholder): 10 min
- Task 7 (Mock endpoint): 10 min
- **Total**: ~180 min (3 hours) for full Phase 5

---

## Ready to Execute?

→ Proceeding with Task 1 (Catalog creation) immediately.
