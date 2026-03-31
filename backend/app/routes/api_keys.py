"""API Key management — read/write provider keys from .env, hot-reload into os.environ."""

import os
import re
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
    return {"success": True, "provider": provider, "env_var": env_var, "masked_value": _mask(value)}


@router.delete("/{provider}")
async def clear_api_key(provider: str):
    """Clear an API key for a provider."""
    if provider not in MANAGED_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    env_var = MANAGED_KEYS[provider]
    env_path = _find_env_file()
    _write_env_key(env_path, env_var, "")
    os.environ.pop(env_var, None)

    logger.info(f"API key cleared for provider: {provider}")
    return {"success": True, "provider": provider}
