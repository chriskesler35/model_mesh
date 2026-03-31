"""Workflow management and ComfyUI integration endpoints."""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from app.middleware.auth import verify_api_key
from pydantic import BaseModel
from typing import List, Optional
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["workflows"], dependencies=[Depends(verify_api_key)])

_WORKFLOW_DIR = Path(__file__).parent.parent.parent.parent / "data" / "workflows"


class WorkflowSummary(BaseModel):
    id: str
    name: str
    description: str
    category: str
    default_checkpoint: str
    default_size: str
    sizes: List[str]
    compatible_checkpoints: List[str]


class WorkflowFull(WorkflowSummary):
    workflow: dict


class WorkflowListResponse(BaseModel):
    data: List[WorkflowSummary]


class CheckpointsResponse(BaseModel):
    checkpoints: List[str]
    unet_models: List[str]
    status: str  # "online" or "offline"


def _load_workflow(workflow_id: str) -> dict:
    """Load a workflow template from disk by ID."""
    path = _WORKFLOW_DIR / f"{workflow_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid workflow JSON: {e}")


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows():
    """List available workflow templates."""
    workflows = []
    if not _WORKFLOW_DIR.exists():
        return WorkflowListResponse(data=[])

    for path in sorted(_WORKFLOW_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            workflows.append(WorkflowSummary(
                id=path.stem,
                name=data.get("name", path.stem),
                description=data.get("description", ""),
                category=data.get("category", "txt2img"),
                default_checkpoint=data.get("default_checkpoint", ""),
                default_size=data.get("default_size", "1024x1024"),
                sizes=data.get("sizes", ["1024x1024"]),
                compatible_checkpoints=data.get("compatible_checkpoints", []),
            ))
        except Exception as e:
            logger.warning(f"Skipping workflow {path.name}: {e}")

    return WorkflowListResponse(data=workflows)


@router.get("/workflows/{workflow_id}", response_model=WorkflowFull)
async def get_workflow(workflow_id: str):
    """Get full workflow template including ComfyUI JSON."""
    data = _load_workflow(workflow_id)
    return WorkflowFull(
        id=workflow_id,
        name=data.get("name", workflow_id),
        description=data.get("description", ""),
        category=data.get("category", "txt2img"),
        default_checkpoint=data.get("default_checkpoint", ""),
        default_size=data.get("default_size", "1024x1024"),
        sizes=data.get("sizes", ["1024x1024"]),
        compatible_checkpoints=data.get("compatible_checkpoints", []),
        workflow=data.get("workflow", {}),
    )


@router.get("/comfyui/checkpoints", response_model=CheckpointsResponse)
async def get_checkpoints():
    """Query ComfyUI for available checkpoints and UNET models."""
    checkpoints: List[str] = []
    unet_models: List[str] = []

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Standard checkpoints
            try:
                r = await client.get("http://localhost:8188/object_info/CheckpointLoaderSimple")
                if r.status_code == 200:
                    info = r.json()
                    ckpt_input = info.get("CheckpointLoaderSimple", {}).get("input", {}).get("required", {})
                    ckpt_list = ckpt_input.get("ckpt_name", [])
                    if isinstance(ckpt_list, list) and len(ckpt_list) > 0:
                        # First element is the list of checkpoint names
                        if isinstance(ckpt_list[0], list):
                            checkpoints = ckpt_list[0]
                        else:
                            checkpoints = ckpt_list
            except Exception as e:
                logger.debug(f"Failed to get checkpoints: {e}")

            # Flux-style UNET models
            try:
                r = await client.get("http://localhost:8188/object_info/UNETLoader")
                if r.status_code == 200:
                    info = r.json()
                    unet_input = info.get("UNETLoader", {}).get("input", {}).get("required", {})
                    unet_list = unet_input.get("unet_name", [])
                    if isinstance(unet_list, list) and len(unet_list) > 0:
                        if isinstance(unet_list[0], list):
                            unet_models = unet_list[0]
                        else:
                            unet_models = unet_list
            except Exception as e:
                logger.debug(f"Failed to get UNET models: {e}")

        return CheckpointsResponse(checkpoints=checkpoints, unet_models=unet_models, status="online")

    except Exception:
        return CheckpointsResponse(checkpoints=[], unet_models=[], status="offline")


@router.get("/comfyui/status")
async def comfyui_status():
    """Check if ComfyUI is running and get system stats."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get("http://localhost:8188/system_stats")
            if r.status_code == 200:
                stats = r.json()
                return {
                    "status": "online",
                    "system_stats": stats,
                }
    except Exception:
        pass

    return {"status": "offline", "system_stats": None}
