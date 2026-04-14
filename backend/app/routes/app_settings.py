"""App settings CRUD — key/value store for configurable options."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.middleware.auth import verify_api_key
from app.models.app_settings import AppSetting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/settings/app", tags=["settings"], dependencies=[Depends(verify_api_key)])

# Default values for known settings
DEFAULTS = {
    "comfyui_dir": "",
    "comfyui_python": "",
    "comfyui_url": "http://localhost:8188",
    "comfyui_gpu_devices": "0",
    "comfyui_launch_args": "",
    "default_image_provider": "gemini",
    "default_workflow": "sdxl-standard",
}


class SettingUpdate(BaseModel):
    value: Optional[str] = None


@router.get("")
async def list_settings(db: AsyncSession = Depends(get_db)):
    """List all app settings with defaults filled in."""
    result = await db.execute(select(AppSetting))
    stored = {s.key: s.to_dict() for s in result.scalars().all()}

    # Merge with defaults
    settings = {}
    for key, default in DEFAULTS.items():
        if key in stored:
            settings[key] = stored[key]
        else:
            settings[key] = {"key": key, "value": default, "updated_at": None}

    # Include any extra stored settings not in DEFAULTS
    for key, val in stored.items():
        if key not in settings:
            settings[key] = val

    return {"data": settings}


@router.get("/{key}")
async def get_setting(key: str, db: AsyncSession = Depends(get_db)):
    """Get a single setting."""
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        return setting.to_dict()
    if key in DEFAULTS:
        return {"key": key, "value": DEFAULTS[key], "updated_at": None}
    return {"key": key, "value": None, "updated_at": None}


@router.put("/{key}")
async def set_setting(key: str, body: SettingUpdate, db: AsyncSession = Depends(get_db)):
    """Set a setting value."""
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = body.value or ""
    else:
        setting = AppSetting(key=key, value=body.value or "")
        db.add(setting)
    await db.commit()
    await db.refresh(setting)
    return setting.to_dict()
