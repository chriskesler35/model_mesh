"""Workflow management and ComfyUI integration endpoints."""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.middleware.auth import verify_api_key
from app.database import get_db
from app.services.app_settings_helper import get_setting
from pydantic import BaseModel
from typing import List, Optional
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["workflows"], dependencies=[Depends(verify_api_key)])

_WORKFLOW_DIR = Path(__file__).parent.parent.parent.parent / "data" / "workflows"


def _convert_editor_to_api(editor_data: dict) -> Optional[dict]:
    """Convert a ComfyUI editor-format workflow (nodes/links) to API format.

    Editor format has 'nodes' array and 'links' array.
    API format has node-ID keys mapping to {class_type, inputs}.
    Returns None if conversion fails.
    """
    nodes = editor_data.get("nodes")
    links = editor_data.get("links")
    if not isinstance(nodes, list) or not isinstance(links, list):
        return None

    # Build link lookup: link_id → (from_node, from_output_idx)
    link_map = {}
    for link in links:
        if isinstance(link, list) and len(link) >= 5:
            link_id, from_node, from_out_idx = link[0], link[1], link[2]
            link_map[link_id] = (str(from_node), from_out_idx)

    api_workflow = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", ""))
        class_type = node.get("type", "")
        if not node_id or not class_type:
            continue

        inputs = {}
        node_inputs = node.get("inputs", [])
        widgets = list(node.get("widgets_values") or [])

        # Map connected inputs (from links)
        for inp in node_inputs:
            if not isinstance(inp, dict):
                continue
            name = inp.get("name", "")
            link_id = inp.get("link")
            if link_id is not None and link_id in link_map:
                from_node, from_idx = link_map[link_id]
                inputs[name] = [from_node, from_idx]

        # Map widget values to unconnected inputs.
        # ComfyUI editor format inserts control widgets (e.g. "randomize",
        # "fixed", "increment", "decrement") after seed/INT inputs.
        # These are NOT real node inputs and must be skipped.
        _CONTROL_WIDGETS = {"fixed", "increment", "decrement", "randomize"}

        unconnected = []
        for inp in node_inputs:
            if not isinstance(inp, dict):
                continue
            name = inp.get("name", "")
            link_id = inp.get("link")
            if link_id is None and name not in inputs:
                unconnected.append((name, inp.get("type", "")))

        wi = 0
        for name, inp_type in unconnected:
            if wi >= len(widgets):
                break
            inputs[name] = widgets[wi]
            wi += 1
            # After INT/seed inputs, skip control widget if present
            if inp_type in ("INT",) and wi < len(widgets) and isinstance(widgets[wi], str) and widgets[wi] in _CONTROL_WIDGETS:
                wi += 1  # skip the control widget

        api_workflow[node_id] = {
            "class_type": class_type,
            "inputs": inputs,
        }

    # Validate: must have at least one output node
    output_types = {"SaveImage", "PreviewImage", "SaveAnimatedWEBP", "SaveAnimatedPNG"}
    has_output = any(
        n.get("class_type") in output_types for n in api_workflow.values()
    )
    if not has_output:
        return None

    return api_workflow


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


def find_workflow_path(workflow_id: str, comfyui_dir: str = "") -> Optional[Path]:
    """Find a workflow .json file by ID across all known directories.

    Search order: built-in (data/workflows/) → ComfyUI/workflows → ComfyUI/user/default/workflows.
    Returns the first match, or None.
    """
    candidates = [_WORKFLOW_DIR / f"{workflow_id}.json"]
    if comfyui_dir:
        base = Path(comfyui_dir)
        candidates.append(base / "workflows" / f"{workflow_id}.json")
        candidates.append(base / "user" / "default" / "workflows" / f"{workflow_id}.json")
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_workflow(workflow_id: str) -> dict:
    """Load a workflow template from disk by ID."""
    path = find_workflow_path(workflow_id)
    if not path:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid workflow JSON: {e}")


def _scan_workflow_dir(directory: Path, seen_ids: set, workflows: list):
    """Scan a directory for workflow .json files and append summaries."""
    if not directory.exists():
        return
    for path in sorted(directory.glob("*.json")):
        wf_id = path.stem
        if wf_id in seen_ids:
            continue  # first-seen wins (built-in > ComfyUI)
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            workflows.append(WorkflowSummary(
                id=wf_id,
                name=data.get("name", wf_id),
                description=data.get("description", ""),
                category=data.get("category", "txt2img"),
                default_checkpoint=data.get("default_checkpoint", ""),
                default_size=data.get("default_size", "1024x1024"),
                sizes=data.get("sizes", ["1024x1024"]),
                compatible_checkpoints=data.get("compatible_checkpoints", []),
            ))
            seen_ids.add(wf_id)
        except Exception as e:
            logger.warning(f"Skipping workflow {path.name}: {e}")


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(db: AsyncSession = Depends(get_db)):
    """List available workflow templates from built-in and ComfyUI directories."""
    workflows = []
    seen_ids: set = set()

    # 1. Built-in workflows (data/workflows/)
    _scan_workflow_dir(_WORKFLOW_DIR, seen_ids, workflows)

    # 2. ComfyUI installation workflow directories
    comfyui_dir = await get_setting("comfyui_dir", db)
    if comfyui_dir:
        comfyui_path = Path(comfyui_dir)
        # Main workflows folder
        _scan_workflow_dir(comfyui_path / "workflows", seen_ids, workflows)
        # User default workflows folder
        _scan_workflow_dir(comfyui_path / "user" / "default" / "workflows", seen_ids, workflows)

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


class LorasResponse(BaseModel):
    loras: List[str]
    status: str  # "online" or "offline"


@router.get("/comfyui/loras", response_model=LorasResponse)
async def get_loras():
    """Query ComfyUI for available LoRA models."""
    loras: List[str] = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("http://localhost:8188/object_info/LoraLoader")
            if r.status_code == 200:
                info = r.json()
                lora_input = info.get("LoraLoader", {}).get("input", {}).get("required", {})
                lora_list = lora_input.get("lora_name", [])
                if isinstance(lora_list, list) and len(lora_list) > 0:
                    if isinstance(lora_list[0], list):
                        loras = lora_list[0]
                    else:
                        loras = lora_list
        return LorasResponse(loras=loras, status="online")
    except Exception:
        return LorasResponse(loras=[], status="offline")


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
