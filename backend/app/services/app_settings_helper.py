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
    "default_image_provider": "gemini",
    "default_workflow": "sdxl-standard",
}

# Env var overrides (highest priority)
_ENV_MAP = {
    "comfyui_url": "COMFYUI_URL",
}


async def get_setting(key: str, db=None) -> str:
    """Get a setting value. Priority: env var > DB > default."""
    # 1. Check env var
    env_key = _ENV_MAP.get(key)
    if env_key:
        env_val = os.environ.get(env_key)
        if env_val:
            return env_val

    # 2. Check DB
    if db:
        try:
            from app.models.app_settings import AppSetting
            result = await db.execute(select(AppSetting).where(AppSetting.key == key))
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                return setting.value
        except Exception as e:
            logger.debug(f"Could not read setting '{key}' from DB: {e}")

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
