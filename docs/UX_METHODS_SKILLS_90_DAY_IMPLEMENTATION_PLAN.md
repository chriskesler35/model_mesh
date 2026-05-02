# DevForgeAI UX + Methods + Skills Implementation Plan

> Created: 2026-04-20
> Scope: 90-day delivery plan + full implementation path
> Objective: Make DevForgeAI highly usable for first-time users and developers while making methods, stacks, skills, and tools easy to discover and install.

## 1. Product Intent

Deliver a unified interface that feels clean, fast, and interactive while preserving advanced capabilities.

Primary outcomes:
- First-time users can start building in under 5 minutes.
- Developers can launch advanced workflows with method stacks in under 60 seconds.
- Users can discover and install skills/tools from GitHub and Hugging Face without deep environment knowledge.

## 2. Guiding UX Principles

- Progressive complexity: Guided Mode by default, Pro Mode on demand.
- Goal-first flow: choose desired outcome before selecting methods/models.
- Explainable automation: always show why method/model/tool was selected.
- Fast feedback: immediate status updates for every user action.
- Reversible actions: safe installs, rollback on failure, clear recovery path.
- Trust and safety: clear permission prompts and sandbox profiles.

## 3. 90-Day Implementation Path

### Days 1-30: UX Foundation + Method Launcher

Goal:
- Reduce cognitive load and improve launch success through guided workflows.

Deliverables:
1. Guided Mode and Pro Mode UI toggle with persistent preference.
2. Goal-first launcher with intent cards:
   - Build MVP
   - Debug project
   - Review implementation
   - Ship release
3. Method Launcher with recommendations for:
   - BMAD
   - Method stack mode
   - GSD
   - Superpowers
   - MVP Loop / Spec Audit where relevant
4. Visual stack composer:
   - Drag-to-order stack
   - Compatibility/conflict warnings
   - Runtime behavior preview
5. Stack presets:
   - Starter
   - Speed Build
   - Deep Audit
   - Solo Creator
   - Team Delivery

Backend scope:
- Method preset API and recommendation endpoint.
- Stack compatibility validator and conflict scoring.

Frontend scope:
- New launch flow in Workbench entry.
- Stack composer panel and preset selector.
- Suggested vs Advanced path split.

Acceptance criteria:
- New users can launch an appropriate pipeline in under 2 minutes.
- Power users can build and launch a custom stack in under 60 seconds.

### Days 31-60: Skills and Tools Marketplace (GitHub + Hugging Face)

Goal:
- Make skills/tools discoverable and installable with minimal technical setup.

Deliverables:
1. Marketplace UI with unified search and filters:
   - Use case
   - Language
   - Complexity
   - Trust level
   - Compatibility
2. Connectors:
   - GitHub metadata ingestion
   - Hugging Face metadata ingestion
3. Skill manifest standard (required for one-click install):
   - Name and purpose
   - Runtime requirements
   - Install steps
   - Health check command
   - Required permissions
   - Compatibility metadata
4. Guided install wizard:
   - Install
   - Validate
   - Rollback on failure
5. Installed skills manager:
   - Enable/disable
   - Update
   - Remove
   - Health status

Backend scope:
- Skill registry tables and indexing.
- Install orchestrator with step telemetry.
- Health check and rollback runner.

Frontend scope:
- Marketplace page and card system.
- Guided install flow with progress timeline.
- Installed skills management view.

Acceptance criteria:
- Compatible skill install in 3 clicks.
- Install failures always end in rollback or guided recovery.

### Days 61-90: Interactivity, Trust, and Iteration Loop

Goal:
- Match high-interactivity workflows while preserving clean UX.

Deliverables:
1. Explainability panel:
   - Why this method stack
   - Why this model/tool
2. Live intervention controls:
   - Pause
   - Reroute method/model
   - Inject guidance
   - Retry from checkpoint
3. Readiness and confidence scoring:
   - Use case coverage
   - Runtime verification status
   - Blocker severity
4. One-click Iteration 2:
   - Generate follow-up run from unmet criteria only
5. Onboarding 2.0:
   - Goal-aware recommendations
   - Beginner-safe defaults

Acceptance criteria:
- First-time users complete a successful first workflow in under 5 minutes.
- Developer workflows retain all advanced controls without regressions.
- Method and skill adoption improves week-over-week.

## 4. Full Implementation Path (Post 90 Days)

### Months 4-5: Team and Governance Layer
- Team-shared method presets and stack libraries.
- Workspace policy profiles (Safe, Balanced, Developer).
- Approval workflows for skill/tool installation.
- Shared project templates and launch recipes.

### Months 6+: Ecosystem and Growth
- Community-published skill packs.
- Verified publisher badges and trust signals.
- Recommendation engine upgrades from usage analytics.
- Optional distribution/monetization model for premium packs.

## 5. Cross-Cutting Workstreams

1. UX and Design System
- Shared component standards, spacing, typography, interaction patterns.

2. Methods and Orchestration
- Presets, compatibility scoring, stack explainability.

3. Skills/Tools Integration
- GitHub/Hugging Face ingestion, manifests, validation.

4. Runtime and Safety
- Sandboxing, permissions, rollback/recovery.

5. Observability and Analytics
- Funnel metrics, time-to-first-value, install success, intervention rates.

6. QA and Research
- Beginner usability tests + developer workflow regression tests.

## 6. Risks and Mitigations

- Risk: Feature overload in Guided Mode.
  - Mitigation: Strict progressive disclosure and default-safe choices.

- Risk: Untrusted external tools.
  - Mitigation: Permission gating, trust badges, sandbox defaults.

- Risk: Install complexity across environments.
  - Mitigation: Manifest standard + guided installer + rollback.

- Risk: Recommendation mismatch.
  - Mitigation: Explainability and quick override options.

## 7. Metrics to Track from Day 1

- Time to first successful launch.
- Time to first completed workflow.
- Method recommendation acceptance rate.
- Stack customization rate.
- Skill install success/failure/rollback rates.
- Weekly active usage split: Guided vs Pro mode.
- User-reported clarity and confidence scores.

## 8. Execution Kickoff (Start Immediately)

### Week 1 Focus

1. Product decisions
- Finalize Guided vs Pro behavior boundaries.
- Freeze Method Launcher recommendation rules v1.
- Approve manifest schema v1.

2. Engineering setup
- Create feature flags:
  - ui_guided_mode
  - method_launcher_v1
  - skills_marketplace_alpha
- Add analytics events for launch and install funnels.

3. Build tasks
- Implement Goal-first launcher skeleton in Workbench flow.
- Implement method preset API and stack compatibility endpoint.
- Scaffold marketplace backend models and API contracts.

4. Validation
- Run 5 beginner walkthroughs and 5 developer walkthroughs.
- Capture friction points and patch before Week 2 starts.

### Week 2 Preview
- Ship stack composer v1.
- Ship method recommendation card UI.
- Ship marketplace search page skeleton with placeholder data.

## 9. Definition of Done for This Plan

This plan is complete when:
- Work is tracked against the 90-day milestones.
- Week 1 kickoff tasks are created as implementation tickets.
- Feature flags and baseline analytics are in place.
- A first guided launch flow is available behind a feature flag.
