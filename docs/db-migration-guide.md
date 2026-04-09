# Database Migration Guide

This document covers the DevForgeAI database migration strategy, including how migrations run in production, backward-compatibility rules, rollback procedures, and backup policies.

## Overview

| Component | Tool | Location |
|-----------|------|----------|
| Migration framework | Alembic | `backend/alembic/` |
| Migration runner | K8s Job (Helm hook) | `k8s/jobs/migrate.yaml` |
| Nightly backups | K8s CronJob | `k8s/jobs/db-backup-cronjob.yaml` |
| Seed data | Python script | `backend/app/seed.py` |
| CI migration tests | GitHub Actions | `.github/workflows/ci.yml` |

## How Migrations Run in Production

Migrations run as a **Kubernetes Job** with Helm `pre-upgrade` and `pre-install` hooks. This means:

1. Developer merges code to `main` → CI builds a new backend image.
2. Helm upgrade is triggered (manually or via CD pipeline).
3. **Before** any pod is replaced, the `db-migrate` Job runs `alembic upgrade head`.
4. If the migration Job **fails**, Helm aborts the upgrade — the old pods keep running.
5. If the migration Job **succeeds**, Helm proceeds to roll out new pods.
6. After migrations, the seed script runs to insert any missing default data.

### Running Migrations Locally

```bash
cd backend

# Apply all pending migrations
alembic upgrade head

# Check current revision
alembic current

# View migration history
alembic history --verbose
```

### Creating a New Migration

```bash
cd backend

# Auto-generate from model changes
alembic revision --autogenerate -m "add_column_x_to_table_y"

# Create an empty migration for manual SQL
alembic revision -m "backfill_column_x"
```

## Backward-Compatibility Rules

All migrations **must** be backward-compatible with the currently running application code. This allows zero-downtime deployments where old pods coexist with the new schema.

### The Three-Phase Pattern

For any column that needs a NOT NULL constraint:

**Phase 1 — Add nullable column** (deploy with migration)
```python
# Migration: add_email_verified_column
op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=True))
```

**Phase 2 — Backfill data** (separate migration, same or next deploy)
```python
# Migration: backfill_email_verified
op.execute("UPDATE users SET email_verified = false WHERE email_verified IS NULL")
```

**Phase 3 — Add constraint** (deploy after backfill is confirmed complete)
```python
# Migration: constrain_email_verified
op.alter_column('users', 'email_verified', nullable=False, server_default=sa.false())
```

### Rules Summary

| Do | Don't |
|----|-------|
| Add columns as `nullable=True` | Drop columns in use by running code |
| Add new tables freely | Rename columns (add new + backfill + drop old) |
| Add indexes concurrently | Add NOT NULL without backfill first |
| Use `server_default` for new required columns | Change column types without a migration plan |
| Keep migrations small and focused | Bundle unrelated changes in one migration |

## Rollback Procedures

### Rolling Back One Migration

```bash
cd backend
alembic downgrade -1
```

### Rolling Back to a Specific Revision

```bash
# List revisions to find the target
alembic history --verbose

# Downgrade to a specific revision
alembic downgrade <revision_hash>
```

### Emergency Rollback Checklist

1. **Pause deployments** — prevent new Helm upgrades.
2. **Take a backup** before rolling back:
   ```bash
   PGPASSWORD=<password> pg_dump -h <host> -U modelmesh -d modelmesh \
     --no-owner --format=custom > emergency-backup-$(date +%Y%m%d-%H%M%S).dump
   ```
3. **Run the downgrade:**
   ```bash
   cd backend
   alembic downgrade -1
   ```
4. **Verify** the application works with the reverted schema.
5. **Roll back the application** to the previous image tag if needed:
   ```bash
   helm rollback devforgeai <previous-revision>
   ```

### When Rollback Is Not Possible

If a migration added data (backfill) or dropped a column, downgrade may lose data. In these cases:

- Restore from the most recent backup (see Backup section below).
- Apply the backup, then re-run any safe migrations.

## Database Backups

### Nightly Automated Backups

A `CronJob` (`k8s/jobs/db-backup-cronjob.yaml`) runs `pg_dump` every night at 02:00 UTC.

- Backups are stored on a PVC at `/backups/`.
- Backups older than 30 days are automatically pruned.
- Optional S3 upload can be enabled by setting the `S3_BUCKET` env var.

### Manual Backup Before Migration

Always take a manual backup before running migrations in production:

```bash
# Port-forward to the postgres pod
kubectl port-forward -n devforgeai svc/postgres 5432:5432

# Run pg_dump locally
PGPASSWORD=<password> pg_dump -h localhost -U modelmesh -d modelmesh \
  --no-owner --format=custom > pre-migration-$(date +%Y%m%d-%H%M%S).dump
```

### Restoring From Backup

```bash
# Restore a backup
PGPASSWORD=<password> pg_restore -h <host> -U modelmesh -d modelmesh \
  --no-owner --clean --if-exists pre-migration-20260409.dump
```

## CI Migration Testing

The CI pipeline (`.github/workflows/ci.yml`) runs two migration checks on every push:

1. **Fresh database migration** — Runs `alembic upgrade head` against an empty PostgreSQL database to verify the full migration chain works from scratch.
2. **Migration + seed** — After migrating, runs the seed script to verify seed data inserts cleanly.

These tests catch:
- Broken migration chains (missing dependencies)
- SQL syntax errors
- Seed script failures against the latest schema

## Seed Data

The seed script (`backend/app/seed.py`) is idempotent — it only inserts data if the database is empty. It seeds:

- **Providers:** Ollama, Anthropic, Google, OpenRouter
- **Models:** Default models for each provider
- **Personas:** Default, Coder, Creative
- **Built-in Agents:** Coder, Researcher (from `DEFAULT_AGENTS` in `agent.py`)

Run the seed script locally:

```bash
cd backend
python -c "
import asyncio
from app.database import async_session
from app.seed import seed_database
async def run():
    async with async_session() as session:
        await seed_database(session)
asyncio.run(run())
"
```
