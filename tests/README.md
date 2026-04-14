# DevForgeAI Test Suite

## Overview

This directory contains the complete test suite for DevForgeAI v0.2.0.

| Component | Type | Tool | Location |
|-----------|------|------|----------|
| Backend API tests | Automated | pytest + httpx | `tests/test_*.py` |
| Frontend E2E tests | Automated | Playwright | `tests/e2e/specs/` |
| Manual test plan | Printable | Human tester | `tests/manual/DEVFORGEAI_TEST_PLAN.md` |

## Quick Start

### Run Everything
```bat
tests\run_all_tests.bat
```

### Backend API Tests Only
```bash
cd G:\Model_Mesh
python -m pytest tests/ -v --tb=short --ignore=tests/e2e --ignore=tests/manual
```

**Options:**
```bash
# Skip slow tests (LLM-dependent)
python -m pytest tests/ -v -m "not slow"

# Skip destructive tests
python -m pytest tests/ -v -m "not destructive"

# Run specific module
python -m pytest tests/test_health.py -v

# Run with detailed output
python -m pytest tests/ -v --tb=long -s
```

### Frontend E2E Tests Only
```bash
cd G:\Model_Mesh\tests\e2e
npm install                        # first time only
npx playwright install chromium    # first time only
npx playwright test
```

**Options:**
```bash
# Run headed (watch browser)
npx playwright test --headed

# Interactive UI mode
npx playwright test --ui

# Generate HTML report
npx playwright test
npx playwright show-report
```

### Manual Test Plan
Open `tests/manual/DEVFORGEAI_TEST_PLAN.md` in a Markdown viewer or print to PDF.

**Coverage:** ~250 manual test cases across 24 sections.

## Prerequisites

### Backend Tests
```bash
pip install pytest httpx pytest-asyncio
```

### Frontend E2E Tests
```bash
cd tests/e2e
npm install
npx playwright install chromium
```

### Both
DevForgeAI must be running:
- Backend: auto-detected from `DEVFORGEAI_URL`, preferring http://localhost:19001 and falling back to http://localhost:19000
- Frontend: http://localhost:3001
- Ollama: http://localhost:11434 (recommended)

## Test Coverage Summary

### Automated API Tests (~120+ tests)
| Module | Endpoints Tested |
|--------|-----------------|
| Health & System | /v1/health, /v1/system/* |
| Models | CRUD + provider filter + sync |
| Personas | CRUD + default protection |
| Conversations | CRUD + messages + image attachment |
| Chat | Completions (requires Ollama/cloud) |
| Agents | CRUD + defaults + persona resolution |
| Images | Gallery CRUD + generation + upload |
| Projects | CRUD + files + templates |
| Workbench | Sessions CRUD + streaming |
| Identity | Soul/User/Identity CRUD + setup |
| Methods | Activate, stack, conflict |
| Collaboration | Users, workspaces, handoff, audit |
| Preferences | CRUD + detection |
| Settings | API keys, app settings |
| Stats | Costs + usage |
| Remote | Health, Tailscale, sessions |
| Workflows | ComfyUI workflows + checkpoints |
| Misc | Tasks, context, hardware, model lookup/sync/validate |

### Automated E2E Tests (~30+ tests)
- All pages load without errors
- Navigation works
- Dark mode toggle
- Chat interface renders
- Slash command palette
- Error handling (404, console errors, unhandled rejections)
- Settings tabs render

### Manual Tests (~250 tests)
- Full UI/UX walkthrough
- First-run wizard
- Live chat with streaming
- Image generation end-to-end
- Workbench real-time features
- Sandbox operations
- Telegram bot
- Remote access via Tailscale
- Performance checks
- Edge cases and error scenarios

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVFORGEAI_URL` | auto-detect (`http://localhost:19001` preferred) | Backend API URL |
| `DEVFORGEAI_KEY` | `modelmesh_local_dev_key` | API bearer token |
| `DEVFORGEAI_FRONTEND_URL` | `http://localhost:3001` | Frontend URL (E2E) |
