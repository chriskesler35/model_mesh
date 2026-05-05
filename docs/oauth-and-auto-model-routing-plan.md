# OAuth Login + Auto Model Routing Plan

Date: 2026-05-05
Scope: secure DevForgeAI with GitHub/Google sign-in, then add policy-driven model auto-selection to reduce cost.

## 1) Current State (verified in code)

- Password + JWT auth already exists in `backend/app/routes/collaboration.py` (`/v1/auth/login`, `/v1/auth/me`, `/v1/auth/logout`).
- GitHub OAuth provider-specific flow already exists in `backend/app/routes/github_oauth.py`.
- Generic OAuth provider framework exists in `backend/app/services/oauth_providers.py` and `backend/app/routes/oauth_generic.py`.
- Frontend login page already lists OAuth providers in `frontend/src/app/auth/login/page.tsx`.
- GitHub callback page exists in `frontend/src/app/auth/github/callback/page.tsx`.
- Model execution and cost accounting already exists in `backend/app/services/model_client.py` and `backend/app/routes/workbench.py`.

## 2) Immediate Security Fixes (before rollout)

1. Remove secrets from `backend/.env` from source control and rotate all exposed tokens.
2. Add startup guardrails in `backend/app/config.py`:
   - fail fast in non-dev when `jwt_secret` is default value.
   - warn if owner key is default.
3. Add `.env` handling policy in docs:
   - commit only `.env.example`.
   - runtime reads from secrets manager (or deployment environment).

## 3) Authentication Product Design

Goal: users can sign in with GitHub or Google; local password login remains optional fallback for self-hosted owner mode.

### 3.1 Session model

- Keep existing JWT model.
- Keep token transport as `Authorization: Bearer <jwt>`.
- Continue fallback to owner key only when explicit local mode is enabled.

### 3.2 Provider behavior

- GitHub:
  - Keep provider-specific flow for Copilot scope (`copilot`) and git repo access (`repo`).
- Google:
  - Enable via generic provider framework using `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`.

### 3.3 Frontend callback handling gap

- Add a generic callback page: `frontend/src/app/auth/[provider]/callback/page.tsx`.
- Behavior:
  1. parse `code`, `state`, and provider from route.
  2. call `GET /v1/auth/{provider}/callback?code=...&state=...`.
  3. store JWT in `devforge_auth_token` and user in `devforge_user`.
  4. redirect to saved path.
- Keep existing `auth/github/callback` page or refactor it to use the generic callback implementation.

## 4) Data Model Hardening (replace JSON file identity store)

Current identity persistence uses `data/collab_users.json`. Move this to DB for concurrency and security.

### 4.1 New tables

Create SQLAlchemy models + Alembic migrations for:

1. `users`
   - id (uuid, pk)
   - username (unique)
   - email (nullable, indexed)
   - display_name
   - role
   - is_active
   - auth_provider (nullable, primary provider)
   - created_at, updated_at, last_active
2. `oauth_accounts`
   - id (uuid, pk)
   - user_id (fk users.id)
   - provider (`github`, `google`)
   - provider_user_id
   - provider_login
   - access_token_encrypted
   - refresh_token_encrypted (nullable)
   - scopes
   - expires_at
   - created_at, updated_at
   - unique(provider, provider_user_id)
3. `user_model_prefs`
   - id (uuid, pk)
   - user_id (fk users.id)
   - preference_json (task policy, allowed providers, budget caps)
   - updated_at
4. `usage_budget`
   - id (uuid, pk)
   - user_id (fk users.id)
   - period_start, period_end
   - hard_limit_usd
   - soft_limit_usd
   - spent_usd
   - status (`ok`, `soft_exceeded`, `hard_blocked`)

### 4.2 Migration path

1. One-time importer reads `data/collab_users.json` and inserts rows.
2. Keep read compatibility for one release (fallback to JSON if no DB record).
3. Remove JSON fallback after successful migration validation.

## 5) Copilot Access & Capability Detection

Important: OAuth login authenticates users, but model entitlement must still be checked by API responses.

### 5.1 Runtime capability probe

Add provider runtime probe service:

- file: `backend/app/services/provider_capabilities.py`
- outputs:
  - available models list
  - support for tool calling
  - support for streaming
  - supports `auto` routing (if provider exposes this)
  - token expiry / reauth required

Expose endpoint:

- `GET /v1/runtime/provider-capabilities`
- optionally user-scoped: uses the requesting user OAuth account.

### 5.2 Model catalog sync

Extend startup/manual sync:

- update `backend/app/routes/model_sync.py` to ingest provider-discovered model list for authenticated user/provider context.
- store with source metadata:
  - `catalog_source = static|provider_runtime`
  - `last_verified_at`

## 6) Auto Model Router (cost-aware)

### 6.1 New router module

Create `backend/app/services/model_router.py` with:

Inputs:
- task type (`chat`, `coding`, `planning`, `analysis`, `tooling`)
- context length estimate
- user budget state
- latency target
- risk level (safe/default/high_accuracy)
- provider capabilities (including auto support)

Outputs:
- selected provider
- selected model
- params (max_tokens, temperature, timeout)
- fallback chain
- reason trace for observability

### 6.2 Routing policy file

Create policy file:

- `backend/app/config/model_routing_policy.yaml`

Example structure:
- global defaults
- per-task class preferences
- escalation thresholds
- provider allow/deny lists
- budget thresholds

### 6.3 Workbench integration point

Integrate in `backend/app/routes/workbench.py`:

1. In `create_session`, support `body.model = "auto"`.
2. Before `_run_turn`, resolve auto selection via `model_router`.
3. Record selected model/provider on session.
4. On failures, use existing fallback chain with router-provided ordering.

### 6.4 API surface

Add endpoints:

- `POST /v1/routing/preview`
  - returns chosen model and reason without executing.
- `PUT /v1/routing/policy`
  - owner/admin update of policy.
- `GET /v1/routing/policy`
  - read current policy.

## 7) Budget and Token Controls

### 7.1 Per-request guards

In `backend/app/routes/workbench.py` and/or `backend/app/services/model_client.py`:

- enforce max output tokens by policy.
- reject request if user is hard-blocked on budget.
- downshift model tier when soft-limit exceeded.

### 7.2 Accurate spend accounting

- continue using existing token capture in stream finalization.
- enrich with per-provider pricing source/version.
- write usage events per request for audit and daily rollups.

## 8) Frontend UX changes

### 8.1 Login

- Keep current password form + OAuth buttons in `frontend/src/app/auth/login/page.tsx`.
- Add clear provider status badges (configured, connected, reauth needed).

### 8.2 Settings

In `frontend/src/app/(main)/settings/page.tsx`:

- add Google connect/reconnect controls next to GitHub.
- show provider capability summary (models count, auto support, token validity).
- add default model mode selector: `fixed` vs `auto`.

### 8.3 Workbench composer

- model selector includes `Auto (recommended)`.
- if `auto`, show chosen model after each run with rationale snippet.

## 9) Test Plan

### 9.1 Backend tests

Add/extend tests under `tests/`:

1. OAuth login success/failure for GitHub and Google callbacks.
2. JWT issuance and `/v1/auth/me` verification.
3. Auto router unit tests:
   - low-budget -> cheaper model
   - high-risk/high-accuracy -> stronger model
   - missing provider capability -> fallback
4. Budget enforcement tests:
   - soft-limit downshift
   - hard-limit block

### 9.2 Frontend tests

1. Login renders configured providers.
2. Callback stores token and redirects.
3. Settings shows capability and route mode.
4. Workbench session with `model=auto` starts and displays selected model.

## 10) Rollout Strategy

1. Phase A: security cleanup + provider capability endpoint.
2. Phase B: Google callback UX completion + DB-backed identity tables.
3. Phase C: model router in preview mode only (`/v1/routing/preview`).
4. Phase D: enable `model=auto` for owner/admin users.
5. Phase E: full rollout with budget policies for all users.

Rollback:
- Feature flag `MODEL_ROUTING_AUTO_ENABLED=false` to force fixed model behavior.

## 11) Acceptance Criteria

1. User can sign in with GitHub or Google and receives JWT.
2. User-specific provider capability status is visible in settings.
3. Workbench accepts `model=auto` and executes with policy-selected model.
4. Budget soft/hard limits are enforced and observable.
5. Logs include routing reason and final cost per request.
6. No plaintext OAuth tokens stored in JSON files.
