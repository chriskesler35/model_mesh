"""API Key management — read/write provider keys from .env, hot-reload into os.environ."""

import os
import re
import uuid as _uuid
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"], dependencies=[Depends(verify_api_key)])

# The .env file we manage — prefer the root one, fall back to backend dir
def _find_env_file() -> Path:
    candidates = [
        Path(__file__).parent.parent.parent.parent / ".env",  # G:\Model_Mesh\.env
        Path(__file__).parent.parent.parent / ".env",         # G:\Model_Mesh\backend\.env
    ]
    for p in candidates:
        if p.exists():
            return p
    # Default to root location even if it doesn't exist yet
    return candidates[0]

# Keys we expose (display name → env var name)
MANAGED_KEYS = {
    "anthropic":  "ANTHROPIC_API_KEY",
    "google":     "GOOGLE_API_KEY",
    "gemini":     "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai":     "OPENAI_API_KEY",
    # Telegram is managed in Settings → Remote, not here
}

def _read_env_file(path: Path) -> dict[str, str]:
    """Parse key=value pairs from .env, preserving all lines."""
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r'^([A-Z0-9_]+)\s*=\s*(.*)$', line.strip())
        if m:
            result[m.group(1)] = m.group(2)
    return result

def _write_env_key(path: Path, key: str, value: str):
    """Update or append a single key in the .env file."""
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    else:
        lines = []

    pattern = re.compile(rf'^{re.escape(key)}\s*=')
    updated = False
    new_lines = []
    for line in lines:
        if pattern.match(line):
            new_lines.append(f"{key}={value}\n")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")

    path.write_text("".join(new_lines), encoding="utf-8")

def _mask(value: Optional[str]) -> Optional[str]:
    """Return a masked version of the key for display."""
    if not value:
        return None
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "••••••••" + value[-4:]


class ApiKeyStatus(BaseModel):
    provider: str
    env_var: str
    is_set: bool
    masked_value: Optional[str]

class SetKeyRequest(BaseModel):
    value: str


@router.get("")
async def list_api_keys():
    """List all managed API keys (masked)."""
    env_path = _find_env_file()
    env_data = _read_env_file(env_path)

    result = []
    for provider, env_var in MANAGED_KEYS.items():
        # Prefer live os.environ, fall back to .env file
        value = os.environ.get(env_var) or env_data.get(env_var)
        result.append(ApiKeyStatus(
            provider=provider,
            env_var=env_var,
            is_set=bool(value),
            masked_value=_mask(value),
        ))
    return {"data": result, "env_file": str(env_path)}


@router.put("/{provider}")
async def set_api_key(provider: str, body: SetKeyRequest):
    """Set an API key for a provider. Updates .env and reloads into os.environ."""
    if provider not in MANAGED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}. Valid: {list(MANAGED_KEYS)}")

    env_var = MANAGED_KEYS[provider]
    value = body.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Key value cannot be empty")

    env_path = _find_env_file()
    _write_env_key(env_path, env_var, value)

    # Hot-reload into os.environ immediately
    os.environ[env_var] = value

    # If gemini key updated, also sync google (and vice versa) so both names work
    if provider == "gemini" and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = value
        _write_env_key(env_path, "GOOGLE_API_KEY", value)
    elif provider == "google":
        os.environ["GEMINI_API_KEY"] = value
        _write_env_key(env_path, "GEMINI_API_KEY", value)

    # Hot-reload Telegram bot config immediately (no restart needed)
    if provider == "telegram_bot_token":
        try:
            import app.routes.telegram_bot as _tg
            _tg.TELEGRAM_BOT_TOKEN = value
            _tg.TELEGRAM_API_URL = f"https://api.telegram.org/bot{value}"
            logger.info("Telegram bot token reloaded live")
        except Exception as e:
            logger.warning(f"Could not hot-reload Telegram token: {e}")

    if provider == "telegram_chat_ids":
        try:
            import app.routes.telegram_bot as _tg
            _tg.AUTHORIZED_CHAT_IDS = [
                int(cid.strip()) for cid in value.split(",") if cid.strip().lstrip("-").isdigit()
            ]
            logger.info(f"Telegram chat IDs reloaded: {_tg.AUTHORIZED_CHAT_IDS}")
        except Exception as e:
            logger.warning(f"Could not hot-reload Telegram chat IDs: {e}")

    logger.info(f"API key updated for provider: {provider} ({env_var})")

    # Auto-sync models for this provider now that its key is available
    synced_models = 0
    if provider in ("anthropic", "google", "gemini", "openai", "openrouter"):
        try:
            from app.routes.model_sync import run_model_sync
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as _db:
                result = await run_model_sync(_db)
                synced_models = len([a for a in result.get("added", []) if a.startswith(f"{provider}/")])
                logger.info(f"Auto-synced {synced_models} {provider} models after key update")
        except Exception as e:
            logger.warning(f"Auto-sync after key update failed (non-fatal): {e}")

    return {
        "success": True,
        "provider": provider,
        "env_var": env_var,
        "masked_value": _mask(value),
        "synced_models": synced_models,
    }


class ClearKeyImpact(BaseModel):
    """Impact report for clearing a provider key."""
    provider: str
    affected_models: list[dict]         # [{id, model_id, display_name}]
    affected_personas: list[dict]        # [{id, name, slot: "primary"|"fallback", current_model_id}]
    affected_agents: list[dict]          # [{id, name, current_model_id}]
    replacement_candidates: list[dict]   # [{id, model_id, display_name, provider_name}]
    has_references: bool


class ClearKeyRequest(BaseModel):
    """Request body for confirming key clear with replacement choices."""
    replacements: Optional[dict[str, str]] = None  # {affected_model_id: replacement_model_id}
    force: bool = False  # clear even if references exist and no replacements given (leaves NULL)


@router.get("/{provider}/clear-impact", response_model=ClearKeyImpact)
async def get_clear_impact(provider: str):
    """Dry-run: show what would happen if we cleared this provider's key.

    Returns affected models, personas, agents, and suggested replacements
    so the UI can prompt the user before actual deletion.
    """
    if provider not in MANAGED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    from sqlalchemy import select, or_
    from app.database import AsyncSessionLocal
    from app.models.model import Model as ModelORM
    from app.models.provider import Provider as ProviderORM
    from app.models import Persona
    from app.models.agent import Agent

    async with AsyncSessionLocal() as db:
        # Find the provider record
        prov_row = await db.execute(
            select(ProviderORM).where(ProviderORM.name == provider)
        )
        prov = prov_row.scalar_one_or_none()

        affected_models = []
        affected_model_ids: set[str] = set()
        if prov:
            models_res = await db.execute(
                select(ModelORM).where(
                    ModelORM.provider_id == prov.id,
                    ModelORM.is_active == True,
                )
            )
            for m in models_res.scalars().all():
                affected_models.append({
                    "id": str(m.id),
                    "model_id": m.model_id,
                    "display_name": m.display_name,
                })
                affected_model_ids.add(str(m.id))

        # Find personas referencing these models
        affected_personas = []
        if affected_model_ids:
            personas_res = await db.execute(select(Persona))
            for p in personas_res.scalars().all():
                if p.primary_model_id and str(p.primary_model_id) in affected_model_ids:
                    affected_personas.append({
                        "id": str(p.id), "name": p.name,
                        "slot": "primary",
                        "current_model_id": str(p.primary_model_id),
                    })
                if p.fallback_model_id and str(p.fallback_model_id) in affected_model_ids:
                    affected_personas.append({
                        "id": str(p.id), "name": p.name,
                        "slot": "fallback",
                        "current_model_id": str(p.fallback_model_id),
                    })

        # Find agents referencing these models
        affected_agents = []
        if affected_model_ids:
            agents_res = await db.execute(select(Agent))
            for a in agents_res.scalars().all():
                if a.model_id and str(a.model_id) in affected_model_ids:
                    affected_agents.append({
                        "id": str(a.id), "name": a.name,
                        "current_model_id": str(a.model_id),
                    })

        # Replacement candidates: other active models (not from this provider)
        candidates = []
        if affected_model_ids:
            other_models_res = await db.execute(
                select(ModelORM, ProviderORM)
                .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
                .where(ModelORM.is_active == True)
                .where(ModelORM.id.notin_([_uuid.UUID(mid) for mid in affected_model_ids]))
            )
            for m, pv in other_models_res.all():
                candidates.append({
                    "id": str(m.id),
                    "model_id": m.model_id,
                    "display_name": m.display_name or m.model_id,
                    "provider_name": pv.name,
                })

    has_refs = bool(affected_personas or affected_agents)
    return ClearKeyImpact(
        provider=provider,
        affected_models=affected_models,
        affected_personas=affected_personas,
        affected_agents=affected_agents,
        replacement_candidates=candidates,
        has_references=has_refs,
    )


@router.delete("/{provider}")
async def clear_api_key(provider: str, body: Optional[ClearKeyRequest] = None):
    """Clear an API key for a provider.

    If the provider has active models referenced by personas/agents:
      - Pass `replacements: {model_id: new_model_id}` to reassign them.
      - Or pass `force: true` to clear anyway (references set to NULL).
      - Otherwise returns 409 with the impact report; caller must confirm.
    """
    if provider not in MANAGED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    body = body or ClearKeyRequest()

    # Check impact — if there are references, require replacements OR force
    impact = await get_clear_impact(provider)
    replacements = body.replacements or {}

    if impact.has_references and not body.force:
        # Verify all affected references have a replacement
        needs_replacement = set()
        for p in impact.affected_personas:
            needs_replacement.add(p["current_model_id"])
        for a in impact.affected_agents:
            needs_replacement.add(a["current_model_id"])

        missing = needs_replacement - set(replacements.keys())
        if missing:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "references_exist",
                    "message": f"Clearing the {provider} key will affect {len(impact.affected_personas)} persona(s) and {len(impact.affected_agents)} agent(s). Provide replacements in the request body or set force=true.",
                    "impact": impact.model_dump(),
                    "missing_replacements": list(missing),
                }
            )

    # Apply reassignments + deactivate models
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.model import Model as ModelORM
    from app.models.provider import Provider as ProviderORM
    from app.models import Persona
    from app.models.agent import Agent

    reassigned_personas = 0
    reassigned_agents = 0
    deactivated_models = 0

    async with AsyncSessionLocal() as db:
        # Reassign persona references
        for p_info in impact.affected_personas:
            new_model_id = replacements.get(p_info["current_model_id"])
            persona = await db.get(Persona, _uuid.UUID(p_info["id"]))
            if not persona:
                continue
            new_uuid = _uuid.UUID(new_model_id) if new_model_id else None
            if p_info["slot"] == "primary":
                persona.primary_model_id = new_uuid
            else:
                persona.fallback_model_id = new_uuid
            reassigned_personas += 1

        # Reassign agent references
        for a_info in impact.affected_agents:
            new_model_id = replacements.get(a_info["current_model_id"])
            agent = await db.get(Agent, _uuid.UUID(a_info["id"]))
            if not agent:
                continue
            agent.model_id = _uuid.UUID(new_model_id) if new_model_id else None
            reassigned_agents += 1

        # Deactivate (not delete) affected models
        for m_info in impact.affected_models:
            model = await db.get(ModelORM, _uuid.UUID(m_info["id"]))
            if model:
                model.is_active = False
                deactivated_models += 1

        await db.commit()

    # Finally clear the key from env + .env file
    env_var = MANAGED_KEYS[provider]
    env_path = _find_env_file()
    _write_env_key(env_path, env_var, "")
    os.environ.pop(env_var, None)

    logger.info(
        f"API key cleared for {provider}: "
        f"deactivated {deactivated_models} models, "
        f"reassigned {reassigned_personas} personas, "
        f"reassigned {reassigned_agents} agents"
    )
    return {
        "success": True,
        "provider": provider,
        "deactivated_models": deactivated_models,
        "reassigned_personas": reassigned_personas,
        "reassigned_agents": reassigned_agents,
    }
