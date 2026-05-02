# Phase 6 Plan: Guided Install Wizard

> Target: Full-featured install flow with progress, rollback, and health checks
> Approach: Frontend-first with mocked install orchestrator
> Commits: 1 per task

## Phase Goal
Enable users to **install skills with confidence** through a guided, step-by-step wizard with real-time progress, clear error handling, and safe rollback on failure.

## Acceptance Criteria
- ✅ Users click "Install" → modal opens with pre-install checks
- ✅ Install shows 5-step progress timeline (download, validate, extract, health_check, finalize)
- ✅ Real-time progress updates (simulated ~10 seconds total)
- ✅ Success path: skill added to installed list, "Installed" badge appears on cards
- ✅ Failure path: step fails gracefully with rollback prompt
- ✅ Users can retry failed install or discard
- ✅ Installed skills persist in local storage (Phase 5 mock → Phase 6 backend)
- ✅ No TypeScript/linting errors

## Work Breakdown

### Task 1: Create Install Wizard Modal Component
**Scope**: `frontend/src/components/marketplace/InstallWizard.tsx`

**Features**:
- Modal with title, current step info, progress bar
- 5 steps shown: Download, Validate, Extract, Health Check, Finalize
- Current step highlighted, completed steps with ✓ badge
- Progress bar showing 0-100%
- Status message updates per step
- "Cancel" button (only before install starts)
- "Retry" button (on failure)
- "Install Another" or "Finish" button (on success)

**State**:
- `step`: current step (0-4)
- `progress`: 0-100
- `status`: "pending" | "downloading" | "validating" | "extracting" | "checking" | "finalizing" | "success" | "failed"
- `error`: error message if failed
- `canRetry`: boolean

**Deliverable**: Reusable install wizard modal

**Commit**: "feat(marketplace): create install wizard modal component"

---

### Task 2: Create Mock Install Orchestrator (Backend)
**Scope**: Add install logic to `backend/app/routes/marketplace.py`

**Endpoints**:
- `POST /v1/marketplace/skill/:skill_id/install` → start install job, return job_id + stream_url
- `GET /v1/marketplace/skill/:skill_id/install/progress/:job_id` → poll install progress

**Mock Behavior**:
```
[0s-2s]   Step 1: Download (0% → 25%)
[2s-4s]   Step 2: Validate (25% → 50%)
[4s-6s]   Step 3: Extract (50% → 75%)
[6s-8s]   Step 4: Health Check (75% → 90%)
[8s-10s]  Step 5: Finalize (90% → 100%)
[10s+]    Success or Simulated Failure (20% chance on health check)
```

**Response**:
```json
{
  "job_id": "install-uuid",
  "skill_id": "langchain",
  "status": "downloading",
  "current_step": 0,
  "progress": 15,
  "step_messages": {
    "0": "Downloading langchain v0.1.0...",
    "1": "Validating package integrity...",
    "2": "Extracting files...",
    "3": "Running health check...",
    "4": "Finalizing installation..."
  }
}
```

**Failure Simulation** (on step 3, 20% chance):
```json
{
  "job_id": "install-uuid",
  "status": "failed",
  "error": "Health check failed: import langchain failed with ModuleNotFoundError",
  "failed_step": 3,
  "can_retry": true
}
```

**Deliverable**: 2 install endpoints with mock progress simulation

**Commit**: "feat(marketplace): add mocked install orchestrator endpoints"

---

### Task 3: Wire Install Wizard into Marketplace Page
**Scope**: Update `frontend/src/app/(main)/marketplace/page.tsx`

**Changes**:
- Import InstallWizard component
- Add install state: `installingSkillId`, `installJobId`, `showInstallWizard`
- Add polling effect: fetch `/progress/:job_id` every 500ms
- Update install status → update installed_skills list on success
- On success: add skill to `installedSkills` state, show "Installed" badge

**Integration**:
- `handleInstallClick(skillId)` → open wizard modal, start install
- Polling continues until status = "success" or "failed"
- On success: update installed skills list
- On failure: show retry/discard options

**Deliverable**: Marketplace page fully wired to install flow

**Commit**: "feat(marketplace): wire install wizard into marketplace page"

---

### Task 4: Persist Installed Skills (Local Storage → Phase 6 Backend)
**Scope**: `frontend/src/hooks/useInstalledSkills.ts` + backend update

**Frontend Hook**:
- `useInstalledSkills()` → returns installedSkills, addSkill, removeSkill, clearAll
- Persists to localStorage under key `devforgeai:installed-skills`
- On component mount: load from localStorage

**Backend Update**:
- Add `POST /v1/skills/:skill_id/add` → add to installed list (mocked)
- Add `DELETE /v1/skills/:skill_id/remove` → remove from installed list
- Phase 5→6 transition: install wizard calls backend to persist

**Deliverable**: Installed skills persisted across page reloads

**Commit**: "feat(marketplace): add installed skills persistence (local storage)"

---

### Task 5: Create Skill Removal Modal
**Scope**: `frontend/src/components/marketplace/RemoveSkillModal.tsx`

**Features**:
- Confirm dialog with skill name
- "Remove" and "Cancel" buttons
- Success toast on removal

**Deliverable**: Simple confirmation modal for skill removal

**Commit**: "feat(marketplace): add skill removal confirmation modal"

---

### Task 6: Add Uninstall Controls to Marketplace
**Scope**: Update `SkillCard.tsx` and `SkillDetailPane.tsx`

**Changes**:
- If skill is installed: show "Remove" button instead of "Install"
- On installed card click: show "Remove" option
- Clicking remove → show confirmation modal
- On confirm: call `DELETE /v1/skills/:skill_id/remove`, update local state

**Deliverable**: Users can remove installed skills

**Commit**: "feat(marketplace): add skill removal from marketplace UI"

---

### Task 7: Add Installed Skills Manager Page (Phase 7 Preview)
**Scope**: `frontend/src/app/(main)/skills/installed/page.tsx` (basic)

**Features**:
- List all installed skills with version, install date
- Health status indicator (mock: all green in Phase 6)
- Enable/disable toggle (mock: no effect)
- Remove button
- Update button (Phase 7)

**Deliverable**: Separate installed skills management page

**Commit**: "feat(marketplace): add installed skills manager page (phase 7 preview)"

---

## Technical Decisions Locked

1. **Mock install duration**: ~10 seconds total (2s per step)
2. **Failure rate**: 20% chance on health check step (for UX testing)
3. **Persistence**: Phase 6 uses localStorage + mocked backend; Phase 7+ will use real DB
4. **Polling**: 500ms interval for progress updates
5. **Job tracking**: In-memory UUID-based job tracking (no database)

## Success Verification

- ✅ Click "Install" on any skill → wizard opens
- ✅ Progress timeline shows all 5 steps
- ✅ Step names update in real time
- ✅ Progress bar reaches 100% after ~10 seconds
- ✅ On success: skill appears in installed list, badge updates
- ✅ On failure (simulate): error message shown, retry button available
- ✅ Retry succeeds on second attempt
- ✅ Remove skill → confirmation modal → skill removed
- ✅ Installed skills persist after page reload
- ✅ Separate installed skills manager page accessible
- ✅ No TypeScript/linting errors

## Effort Estimate

- Task 1 (Wizard modal): 45 min
- Task 2 (Backend orchestrator): 30 min
- Task 3 (Wiring): 40 min
- Task 4 (Persistence): 20 min
- Task 5 (Remove modal): 15 min
- Task 6 (Uninstall UI): 20 min
- Task 7 (Manager page): 30 min
- **Total**: ~200 min (3.5 hours)

---

## Ready to Execute?

→ Proceeding with Task 1 (InstallWizard component) immediately.
