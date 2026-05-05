"""API Key management — read/write provider keys from .env, hot-reload into os.environ."""

import os
import re
import shutil
import subprocess
import uuid as _uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.middleware.auth import verify_api_key
from app.services.codex_oauth import (
    get_codex_oauth_tokens,
    get_codex_proxy_base_url,
    get_codex_proxy_configuration_issue,
    is_codex_proxy_reachable,
    is_default_codex_proxy_base_url,
    codex_proxy_url_is_supported,
    write_codex_cli_auth,
)
from app.services.github_copilot import verify_copilot_access, get_copilot_auth_token_with_source, get_copilot_auth_token
from app.services.provider_credentials import get_provider_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"], dependencies=[Depends(verify_api_key)])

def _env_candidates() -> list[Path]:
    return [
        Path(__file__).parent.parent.parent.parent / ".env",  # repo root
        Path(__file__).parent.parent.parent / ".env",         # backend/.env
    ]


# Canonical file for response metadata and first-write bootstrap.
def _find_env_file() -> Path:
    for p in _env_candidates():
        if p.exists():
            return p
    return _env_candidates()[0]


def _existing_env_files() -> list[Path]:
    existing = [p for p in _env_candidates() if p.exists()]
    return existing or [_find_env_file()]


def _read_env_merged() -> dict[str, str]:
    """Return merged env values from all known .env files.

    Precedence: backend/.env overrides root .env when both define the same key,
    which mirrors how local backend launches typically resolve settings.
    """
    merged: dict[str, str] = {}
    for path in _env_candidates():
        merged.update(_read_env_file(path))
    return merged


def _write_env_key_all(key: str, value: str) -> None:
    for path in _existing_env_files():
        _write_env_key(path, key, value)

# Keys we expose (display name → env var name)
MANAGED_KEYS = {
    "anthropic":  "ANTHROPIC_API_KEY",
    "google":     "GOOGLE_API_KEY",
    "gemini":     "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai":     "OPENAI_API_KEY",
    "github-copilot": "GITHUB_COPILOT_TOKEN",
    "codex-proxy": "CODEX_OAUTH_PROXY_BASE_URL",
    "openai-oauth": "OPENAI_OAUTH_ACCESS_TOKEN",
    # Telegram is managed in Settings → Remote, not here
}

CONFIG_ONLY_KEYS = {"codex-proxy"}

MODEL_PROVIDER_ALIASES = {
    "codex-proxy": "openai-codex",
    "openai-oauth": "openai-codex",
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


def _provider_model_name(provider: str) -> str:
    return MODEL_PROVIDER_ALIASES.get(provider, provider)


def _get_collaboration_user_token_count() -> int:
    users_file = Path(__file__).parent.parent.parent.parent / "data" / "collab_users.json"
    if not users_file.exists():
        return 0
    try:
        import json
        users = json.loads(users_file.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if isinstance(users, dict):
        iterable = users.values()
    elif isinstance(users, list):
        iterable = users
    else:
        return 0
    return sum(
        1
        for user in iterable
        if isinstance(user, dict) and (user.get("github_token") or "").strip()
    )


def _get_runtime_credential_status() -> dict:
    codex_cli_path = shutil.which("codex")
    codex_cli_installed = bool(codex_cli_path)
    codex_cli_logged_in = False
    codex_cli_login_status = None
    if codex_cli_installed:
        try:
            result = subprocess.run(
                [codex_cli_path, "login", "status"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            codex_cli_login_status = (result.stdout or result.stderr or "").strip() or None
            codex_cli_logged_in = result.returncode == 0 and "logged in" in (codex_cli_login_status or "").lower()
        except Exception as exc:
            codex_cli_login_status = f"Status check failed: {type(exc).__name__}"

    codex_tokens = get_codex_oauth_tokens()
    access_token = codex_tokens.get("access_token")
    refresh_token = codex_tokens.get("refresh_token")
    proxy_base_url = get_codex_proxy_base_url()
    proxy_reachable = is_codex_proxy_reachable()
    proxy_url_supported = codex_proxy_url_is_supported()
    configuration_issue = get_codex_proxy_configuration_issue()
    auth_ready = bool(access_token or refresh_token or codex_cli_logged_in)
    proxy_env_override = bool(os.environ.get("CODEX_OAUTH_PROXY_BASE_URL"))
    has_openai_api_key = bool(get_provider_api_key("openai"))

    proxy_usable = auth_ready and proxy_reachable and proxy_url_supported
    # OpenAI API key path is always usable independently of the OAuth proxy
    overall_usable = proxy_usable or has_openai_api_key

    if has_openai_api_key:
        usability_summary = "OpenAI API key is configured — OpenAI and Codex models are available."
        recommended_action = None
    elif proxy_usable:
        usability_summary = "Authentication and an OpenAI-compatible HTTP proxy are both ready."
        recommended_action = None
    elif configuration_issue:
        usability_summary = (
            "Codex CLI is authenticated (ChatGPT mode), but its app-server does not expose an HTTP API. "
            "The ChatGPT OAuth token cannot be used directly as an OpenAI API key."
        )
        recommended_action = (
            "Add an OPENAI_API_KEY (sk-…) from platform.openai.com/api-keys to the OpenAI provider. "
            "Alternatively, set CODEX_OAUTH_PROXY_BASE_URL to a custom OpenAI-compatible HTTP bridge."
        )
    elif auth_ready:
        usability_summary = (
            "Codex CLI is authenticated, but no OpenAI API key or compatible HTTP proxy is configured. "
            "The ChatGPT OAuth token works for the standalone codex CLI tool only."
        )
        recommended_action = (
            "Add an OPENAI_API_KEY (sk-…) from platform.openai.com/api-keys to enable OpenAI models in DevForgeAI."
        )
    else:
        usability_summary = (
            "No OpenAI credentials are configured. "
            "Add an OPENAI_API_KEY from platform.openai.com/api-keys, or install and log in to the Codex CLI."
        )
        recommended_action = "Set OPENAI_API_KEY in the OpenAI provider section, or install the Codex CLI and log in."

    github_token, github_source = get_copilot_auth_token_with_source()
    collab_user_count = _get_collaboration_user_token_count()

    return {
        "openai_oauth": {
            "provider": "openai-codex",
            "has_access_token": bool(access_token),
            "masked_access_token": _mask(access_token),
            "has_refresh_token": bool(refresh_token),
            "codex_cli_installed": codex_cli_installed,
            "codex_cli_logged_in": codex_cli_logged_in,
            "codex_cli_status": codex_cli_login_status,
            "auth_file": codex_tokens.get("auth_file"),
            "proxy_base_url": proxy_base_url,
            "proxy_reachable": proxy_reachable,
            "proxy_url_supported": proxy_url_supported,
            "proxy_env_override": proxy_env_override,
            "using_default_proxy_url": is_default_codex_proxy_base_url(),
            "configuration_issue": configuration_issue,
            "auth_ready": auth_ready,
            "has_openai_api_key": has_openai_api_key,
            "usable": overall_usable,
            "usability_summary": usability_summary,
            "recommended_action": recommended_action,
        },
        "github_copilot": {
            "provider": "github-copilot",
            "has_token": bool(github_token),
            "masked_token": _mask(github_token),
            "source": github_source,
            "usable": False,
            "collaboration_user_count": collab_user_count,
            "oauth_configured": bool(os.environ.get("GITHUB_CLIENT_ID") and os.environ.get("GITHUB_CLIENT_SECRET")),
            "live_verified": False,
            "validation_error": None,
        },
    }


def _launch_detached_process(command: list[str], cwd: Optional[str] = None) -> None:
    kwargs = {
        "cwd": cwd,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


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
    env_data = _read_env_merged()

    result = []
    for provider, env_var in MANAGED_KEYS.items():
        if provider == "openai-oauth":
            codex_tokens = get_codex_oauth_tokens()
            value = codex_tokens.get("access_token")
        else:
            # Prefer live os.environ, fall back to .env file
            value = os.environ.get(env_var) or env_data.get(env_var)
        result.append(ApiKeyStatus(
            provider=provider,
            env_var=env_var,
            is_set=bool(value),
            masked_value=_mask(value),
        ))
    return {"data": result, "env_file": str(env_path)}


@router.get("/runtime-status")
async def runtime_status():
    """Return live usability details for OAuth-backed provider credentials."""
    status = _get_runtime_credential_status()
    github_token = (get_copilot_auth_token() or "").strip()
    if github_token:
        live_verified, validation_error = await verify_copilot_access(github_token)
        status["github_copilot"]["live_verified"] = live_verified
        status["github_copilot"]["validation_error"] = validation_error
        status["github_copilot"]["usable"] = live_verified
        # Check if the token has the copilot scope by trying the session token exchange.
        # If it returns a different (longer) token it means the exchange succeeded.
        from app.services.github_copilot import exchange_for_copilot_token
        session_token = await exchange_for_copilot_token(github_token)
        has_copilot_scope = bool(session_token and session_token != github_token)
        status["github_copilot"]["has_copilot_scope"] = has_copilot_scope
    return status


@router.post("/openai-oauth/launch-cli-login")
async def launch_codex_cli_login():
    """Launch Codex CLI device-auth login locally for the current desktop session."""
    codex_cli_path = shutil.which("codex")
    if not codex_cli_path:
        raise HTTPException(status_code=404, detail="Codex CLI is not installed on this machine")

    try:
        status_result = subprocess.run(
            [codex_cli_path, "login", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        current_status = (status_result.stdout or status_result.stderr or "").strip()
        if status_result.returncode == 0 and "logged in" in current_status.lower():
            return {
                "success": True,
                "started": False,
                "already_logged_in": True,
                "message": current_status,
            }
    except Exception:
        current_status = None

    try:
        _launch_detached_process([codex_cli_path, "login", "--device-auth"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not launch Codex CLI login: {exc}") from exc

    return {
        "success": True,
        "started": True,
        "already_logged_in": False,
        "message": "Codex CLI device-auth login launched. Finish the browser/device flow, then refresh runtime status.",
    }


@router.put("/{provider}")
async def set_api_key(provider: str, body: SetKeyRequest):
    """Set an API key for a provider. Updates .env and reloads into os.environ."""
    if provider not in MANAGED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}. Valid: {list(MANAGED_KEYS)}")

    env_var = MANAGED_KEYS[provider]
    value = body.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Key value cannot be empty")
    if provider == "codex-proxy" and not re.match(r"^https?://", value, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Codex proxy URL must start with http:// or https://")

    env_path = _find_env_file()
    _write_env_key_all(env_var, value)

    # Hot-reload into os.environ immediately
    os.environ[env_var] = value

    if provider == "openai-oauth":
        write_codex_cli_auth(access_token=value)

    # If gemini key updated, also sync google (and vice versa) so both names work
    if provider == "gemini" and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = value
        _write_env_key_all("GOOGLE_API_KEY", value)
    elif provider == "google":
        os.environ["GEMINI_API_KEY"] = value
        _write_env_key_all("GEMINI_API_KEY", value)

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
    sync_targets = {
        "anthropic": {"anthropic"},
        "google": {"google"},
        "gemini": {"google"},
        "openai": {"openai"},
        "openrouter": {"openrouter"},
        "github-copilot": {"github-copilot"},
        "codex-proxy": {"openai-codex"},
        "openai-oauth": {"openai-codex"},
    }.get(provider, set())

    if sync_targets:
        try:
            from app.routes.model_sync import run_model_sync
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as _db:
                result = await run_model_sync(_db)
                synced_models = len([
                    added_model for added_model in result.get("added", [])
                    if added_model.split("/", 1)[0] in sync_targets
                ])
                logger.info(f"Auto-synced {synced_models} model(s) after key update for {provider}")
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
    if provider in CONFIG_ONLY_KEYS:
        raise HTTPException(status_code=400, detail=f"{provider} is a runtime configuration key and cannot be provider-cleared")

    from sqlalchemy import select, or_
    from app.database import AsyncSessionLocal
    from app.models.model import Model as ModelORM
    from app.models.provider import Provider as ProviderORM
    from app.models import Persona
    from app.models.agent import Agent

    async with AsyncSessionLocal() as db:
        # Find the provider record
        prov_row = await db.execute(
            select(ProviderORM).where(ProviderORM.name == _provider_model_name(provider))
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

    if provider in CONFIG_ONLY_KEYS:
        env_var = MANAGED_KEYS[provider]
        env_path = _find_env_file()
        _write_env_key_all(env_var, "")
        os.environ.pop(env_var, None)
        logger.info(f"Runtime config key cleared for {provider}")
        return {
            "success": True,
            "provider": provider,
            "deactivated_models": 0,
            "reassigned_personas": 0,
            "reassigned_agents": 0,
        }

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
        provider_row = await db.execute(
            select(ProviderORM).where(ProviderORM.name == _provider_model_name(provider))
        )
        provider_record = provider_row.scalar_one_or_none()

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
                model.validation_status = "failed"
                model.validation_source = "provider_removed"
                model.validation_warning = "Provider was removed or disconnected, so this model is unavailable."
                model.validation_error = "provider_removed"
                deactivated_models += 1

        if provider_record:
            provider_record.is_active = False
            provider_record.config = {
                **(provider_record.config or {}),
                "removed_at": datetime.utcnow().isoformat(),
                "removal_reason": "provider_cleared_from_settings",
            }

        await db.commit()

    # Finally clear the key from env + .env file
    env_var = MANAGED_KEYS[provider]
    env_path = _find_env_file()
    _write_env_key_all(env_var, "")
    os.environ.pop(env_var, None)
    if provider == "openai-oauth":
        write_codex_cli_auth(access_token="")

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
