# Model Cleanup & Resync Guide

## Overview

You now have two ways to clean up junk models and reset to only active catalog models:

1. **HTTP API Endpoint** — `/v1/models/cleanup` (POST)
2. **CLI Script** — `python -m app.scripts.manage_models`

## Quick Start

### Option 1: Using the CLI (Recommended)

The CLI provides interactive confirmation and detailed feedback.

```bash
# From the Model_Mesh root directory:

# View current model inventory
cd backend
python -m app.scripts.manage_models status

# Clean all models and resync fresh
python -m app.scripts.manage_models cleanup

# Run sync without deleting (upsert mode - adds/updates only)
python -m app.scripts.manage_models sync
```

### Option 2: Using the HTTP Endpoint

```bash
# Replace with your actual backend URL and API key
curl -X POST \
  "http://localhost:19001/v1/models/cleanup" \
  -H "Authorization: Bearer YOUR_API_KEY"

# Or using PowerShell:
Invoke-WebRequest -Uri "http://localhost:19001/v1/models/cleanup" `
  -Method POST `
  -Headers @{"Authorization"="Bearer YOUR_API_KEY"} | ConvertTo-Json
```

## What Each Command Does

### `manage_models status`
Shows current model inventory grouped by provider:
- Total count per provider
- Active vs inactive model breakdown
- Validation status of each model
- Display names and model IDs

**No changes made — safe to run anytime.**

### `manage_models cleanup`
⚠️ **DESTRUCTIVE** — Requires confirmation

1. Displays current model count
2. Asks for confirmation (type 'yes')
3. Deletes ALL models from the database
4. Resets provider configurations
5. Runs fresh sync from provider catalogs
6. Only keeps models that are currently active in each provider's catalog

**Impact:**
- All models marked as inactive/junk are permanently deleted
- References in personas, agents, and request logs become NULL
- Fresh models are discovered from:
  - Ollama (if running and reachable)
  - Anthropic, OpenAI, Google, OpenRouter, GitHub Copilot (if API keys configured)

### `manage_models sync`
Safe sync mode — adds/updates without deleting

- Discovers current models from provider catalogs
- Adds any NEW models found
- Updates pricing/capabilities for existing models
- Marks models as inactive if they're no longer in provider catalogs
- **Does NOT delete** old models

Use this if you want to update without full cleanup.

## Understanding the Output

### Status Command Output Example
```
MODEL INVENTORY BY PROVIDER
==============================

📦 ANTHROPIC - 6 active, 0 inactive (total: 6)
  ACTIVE MODELS:
    ✓ claude-opus-4-5                       [validated]
    ✓ claude-sonnet-4-5                     [validated]
    ⚠ claude-haiku-4-5                      [unverified]

📦 OLLAMA - 3 active, 0 inactive (total: 3)
  ACTIVE MODELS:
    ✓ llama2:latest                         [validated]
    ...
```

### Cleanup Command Output Example
```
CLEANUP AND RESYNC COMPLETE
==============================
Deleted:     47 old models
Added:       23 fresh models
Ollama:      3 models
Paid APIs:   20 models

Per-Provider Summary:
  • anthropic          ✓ ACTIVE      | Discovered: 6   | Added: 6   | Deprecated: 0
  • openai             ✓ ACTIVE      | Discovered: 5   | Added: 5   | Deprecated: 0
  • google             ✓ ACTIVE      | Discovered: 4   | Added: 4   | Deprecated: 0
  • ollama             ✓ ACTIVE      | Discovered: 3   | Added: 3   | Deprecated: 0
  • openrouter         ✗ NOT CONFIGURED (no API key)
```

## When to Use Each Approach

| Situation | Command |
|-----------|---------|
| Check what models you have | `status` |
| Many junk/deprecated models accumulated | `cleanup` |
| Regular update with new models available | `sync` |
| Auto-remove models no longer in provider catalogs | `sync` (runs automatically) |
| Update pricing/capabilities for existing models | `sync` |

## How the Cleanup Works

### Before Cleanup
```
Database has:
- 47 total models
- 23 active (in provider catalogs)
- 24 inactive (deprecated, missing from catalogs)
- 8 duplicates (same model_id, different versions)
- Pricing/capabilities from old syncs
```

### After Cleanup
```
Database has:
- 23 total models
- 23 active (fresh from provider catalogs)
- 0 inactive (junk removed)
- 0 duplicates (deduplicated during sync)
- Current pricing/capabilities
```

### Safety Features
✓ Foreign keys with `ondelete="SET NULL"` protect data:
  - Personas with deleted models → model_id becomes NULL
  - Agents with deleted models → model_id becomes NULL
  - Request logs with deleted models → model_id becomes NULL

✓ Confirmation required before deletion

✓ Full transaction (all-or-nothing - won't leave DB in inconsistent state)

✓ Detailed logging and error reporting

## Configuration

Models are discovered from providers based on your `.env` configuration:

```env
# If set, Ollama models are synced
OLLAMA_BASE_URL=http://localhost:11434

# If set, enables that provider's models
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
OPENROUTER_API_KEY=...
```

Cleanup respects all configured providers — it will only fetch from providers that have API keys set.

## Troubleshooting

### "Ollama not reachable"
- Ensure Ollama is running on the configured URL
- Check `OLLAMA_BASE_URL` in `.env`
- Command continues anyway with just API provider models

### "No API key set for provider X"
- Add the API key to `.env`
- Run `cleanup` or `sync` again
- That provider's models will now be discovered

### "Fresh sync failed after cleanup"
- Check error message for which provider failed
- Verify API keys and network connectivity
- Old models are already deleted (see logs for recovery if needed)
- Consider running `sync` to retry just that provider

### Models seem to disappear after cleanup
✓ **This is expected!** Models not in active provider catalogs are deleted.
  - Deprecated/retired models are removed
  - Old snapshots are removed
  - Only current, active models are kept

If you need a specific old model back:
1. Check the provider catalog if it's still available
2. Set up credentials for that provider
3. Run `sync` to re-discover it

## Advanced: Manual HTTP Endpoint Usage

If using the HTTP endpoint directly, the response includes:

```json
{
  "ok": true,
  "cleanup": {
    "deleted_models": 47,
    "models_before": 50
  },
  "fresh_sync": {
    "added": ["anthropic/claude-opus-4-5", "..."],
    "skipped_existing": 0,
    "ollama_models": 3,
    "paid_models": 20,
    "provider_details": {
      "anthropic": {
        "configured": true,
        "source": "provider_api",
        "discovered": 6,
        "added": 6,
        "deactivated": 0
      }
    }
  },
  "message": "Cleanup complete. 47 junk models removed. Fresh sync added 23 active models."
}
```

## Questions?

For detailed logs, check the backend logs while cleanup runs:
```bash
# In another terminal, watch logs
tail -f logs/backend.log | grep -i "model"
```
