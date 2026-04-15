"""Helper to read app settings from DB, with env fallback."""

import os
import logging
from typing import Optional
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Defaults matching the route defaults
_DEFAULTS = {
    "comfyui_dir": "",
    "comfyui_python": "",
    "comfyui_url": "http://localhost:8188",
    "comfyui_gpu_devices": "0",
    "comfyui_launch_args": "",
    "comfyui_poll_timeout_seconds": "1800",
    "comfyui_long_load_mode": "0",
    "default_image_provider": "gemini",
    "default_workflow": "sdxl-standard",
    "remote_tailscale_frontend_url": "",
    "remote_tailscale_backend_url": "",
    "remote_wireguard_frontend_url": "",
    "remote_wireguard_backend_url": "",
}

# Env var overrides (highest priority)
_ENV_MAP = {
    "comfyui_url": "COMFYUI_URL",
    "comfyui_poll_timeout_seconds": "COMFYUI_POLL_TIMEOUT_SECONDS",
    "comfyui_long_load_mode": "COMFYUI_LONG_LOAD_MODE",
}


async def get_setting(key: str, db=None) -> str:
    """Get a setting value. Priority: DB > env var > default.

    Runtime settings changed in the UI should take effect immediately, even
    when legacy environment variables like COMFYUI_URL are still present.
    """
    # 1. Check DB first
    if db:
        try:
            from app.models.app_settings import AppSetting
            result = await db.execute(select(AppSetting).where(AppSetting.key == key))
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                return setting.value
        except Exception as e:
            logger.debug(f"Could not read setting '{key}' from DB: {e}")

    # 2. Check env var
    env_key = _ENV_MAP.get(key)
    if env_key:
        env_val = os.environ.get(env_key)
        if env_val:
            return env_val

    # 3. Default
    return _DEFAULTS.get(key, "")


async def get_comfyui_config(db=None) -> dict:
    """Get all ComfyUI-related settings as a dict."""
    return {
        "dir": await get_setting("comfyui_dir", db),
        "python": await get_setting("comfyui_python", db),
        "url": await get_setting("comfyui_url", db),
        "gpu_devices": await get_setting("comfyui_gpu_devices", db),
        "launch_args": await get_setting("comfyui_launch_args", db),
    }
