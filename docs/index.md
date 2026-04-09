# DevForgeAI — Project Documentation Index

> Generated: 2026-04-08 | Scan Level: Exhaustive | Mode: Initial Scan

## Project Overview

- **Type:** Multi-part repository with 3 parts
- **Primary Languages:** Python (backend), TypeScript (frontend, extension)
- **Architecture:** Service-oriented FastAPI backend + App Router Next.js frontend + VS Code extension

## Quick Reference

### Backend (Python FastAPI)
- **Stack:** Python 3.11+, FastAPI, SQLAlchemy async, Alembic, LiteLLM, Redis
- **Database:** SQLite (dev) / PostgreSQL (prod)
- **Entry Point:** `backend/app/main.py`
- **API Routes:** 33 route groups, OpenAI-compatible chat API
- **Models:** 18 database tables
- **Services:** 16 business logic modules

### Frontend (Next.js)
- **Stack:** Next.js 14.1.0, React 18, TypeScript 5.3, Tailwind CSS 3.4
- **Entry Point:** `frontend/src/app/layout.tsx`
- **Pages:** 30+ routes across (main) group + standalone pages
- **Components:** 6 reusable + numerous page-local components
- **Real-time:** SSE streaming + polling

### Extension (VS Code)
- **Stack:** TypeScript 5.3, VS Code API ^1.85.0
- **Entry Point:** `extension/src/extension.ts`
- **Commands:** 4 registered (3 in Command Palette)
- **API Endpoints:** POST /v1/chat/completions, GET /v1/personas

## Generated Documentation

### Architecture
- [Project Overview](./project-overview.md) — Executive summary, features, supported providers
- [Architecture — Backend](./architecture-backend.md) — Service-oriented Python FastAPI architecture
- [Architecture — Frontend](./architecture-frontend.md) — Next.js App Router, state management, real-time patterns
- [Architecture — Extension](./architecture-extension.md) — VS Code command-based architecture + 5 known issues
- [Integration Architecture](./integration-architecture.md) — How backend, frontend, and extension communicate
- [Source Tree Analysis](./source-tree-analysis.md) — Annotated directory structure with file descriptions

### API & Data
- [API Contracts — Backend](./api-contracts-backend.md) — All 130+ REST endpoints across 34 route groups
- [Data Models — Backend](./data-models-backend.md) — 18 SQLAlchemy models with ER relationships + migration strategy

### Components & UI
- [Component Inventory — Frontend](./component-inventory-frontend.md) — Reusable + page-local components, design system patterns

### Development
- [Development Guide](./development-guide.md) — Prerequisites, installation, running, testing, building

## Existing Documentation

- [README.md](../README.md) — Main project README
- [CHARTER.md](../CHARTER.md) — Project charter
- [DEVFORGEAI_SPEC.md](../DEVFORGEAI_SPEC.md) — Product specification
- [INSTALL.md](../INSTALL.md) — Installation guide
- [TEST_PLAN.md](../TEST_PLAN.md) — Test plan
- [API Reference (original)](./api.md) — Original API documentation
- [Deployment Guide (original)](./deployment.md) — Original deployment documentation
- [Personas Reference](./personas.md) — Persona definitions
- [Design Spec](./superpowers/specs/2026-03-27-modelmesh-design.md) — Original design specification
- [Implementation Plan](./superpowers/plans/2026-03-27-modelmesh-implementation.md) — Original implementation plan
- [Extension README](../extension/README.md) — VS Code extension readme
- [Tests README](../tests/README.md) — Test suite documentation

## Getting Started

1. **New to the project?** Start with [Project Overview](./project-overview.md)
2. **Setting up dev environment?** See [Development Guide](./development-guide.md)
3. **Understanding the API?** Read [API Contracts](./api-contracts-backend.md)
4. **Working on the database?** See [Data Models](./data-models-backend.md)
5. **Frontend work?** Read [Architecture — Frontend](./architecture-frontend.md) then [Component Inventory](./component-inventory-frontend.md)
6. **Extension work?** Read [Architecture — Extension](./architecture-extension.md) (note the 5 known issues)
7. **Understanding how parts connect?** See [Integration Architecture](./integration-architecture.md)
8. **Planning a brownfield PRD?** Point the PRD workflow to this `index.md` as input
