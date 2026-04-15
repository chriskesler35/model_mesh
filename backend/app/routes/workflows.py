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


_CONTROL_WIDGETS = {"fixed", "increment", "decrement", "randomize"}

# Cache for ComfyUI object_info schemas: {comfyui_url: {class_type: [input_name, ...]}}
_OBJECT_INFO_CACHE: dict[str, dict[str, list[str]]] = {}


def _parse_comfyui_urls(url_value: str) -> List[str]:
    """Parse one or more ComfyUI base URLs from settings."""
    raw = (url_value or "").strip()
    if not raw:
        return ["http://localhost:8188"]

    urls: List[str] = []
    for chunk in raw.replace(";", ",").replace("\n", ",").split(","):
        url = chunk.strip().rstrip("/")
        if url and url not in urls:
            urls.append(url)
    return urls or ["http://localhost:8188"]


async def _get_running_comfyui_url(db: AsyncSession, timeout: float = 3.0) -> Optional[str]:
    """Return the first configured ComfyUI URL that responds to /system_stats."""
    configured = await get_setting("comfyui_url", db)
    urls = _parse_comfyui_urls(configured)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for url in urls:
            try:
                r = await client.get(f"{url}/system_stats")
                if r.status_code == 200:
                    return url
            except Exception:
                continue
    return None


async def _fetch_object_info_schema(comfyui_url: str) -> dict[str, list[str]]:
    """Fetch the ordered required-input names for every node class from ComfyUI.

    Returns {class_type: [input_name_1, input_name_2, ...]} — the ORDER matches
    how widget values are laid out in the editor format. Cached per-URL.
    """
    if comfyui_url in _OBJECT_INFO_CACHE:
        return _OBJECT_INFO_CACHE[comfyui_url]

    schema: dict[str, list[str]] = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{comfyui_url.rstrip('/')}/object_info")
            if r.status_code == 200:
                info = r.json()
                for class_type, class_info in info.items():
                    input_spec = class_info.get("input", {})
                    required = input_spec.get("required", {})
                    optional = input_spec.get("optional", {})
                    # Preserve insertion order (Python 3.7+ dicts are ordered)
                    names = list(required.keys()) + list(optional.keys())
                    schema[class_type] = names
    except Exception as e:
        logger.warning(f"Failed to fetch ComfyUI /object_info: {e}")

    _OBJECT_INFO_CACHE[comfyui_url] = schema
    return schema


def _convert_editor_to_api(editor_data: dict, node_schema: Optional[dict] = None) -> Optional[dict]:
    """Convert a ComfyUI editor-format workflow (nodes/links) to API format.

    Editor format has 'nodes' array and 'links' array.
    API format has node-ID keys mapping to {class_type, inputs}.

    Args:
        editor_data: The editor-format workflow JSON.
        node_schema: {class_type: [input_name, ...]} from ComfyUI's /object_info.
                     When provided, lets us resolve widget values to input names
                     even when the editor 'inputs' array doesn't list them.
                     Without it, we fall back to only mapping explicitly-listed
                     inputs (which breaks many real-world workflows).

    Returns None if conversion fails.
    """
    nodes = editor_data.get("nodes")
    links = editor_data.get("links")
    if not isinstance(nodes, list) or not isinstance(links, list):
        return None

    node_schema = node_schema or {}

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

        # Track which input names came from links (already resolved to [node, idx])
        connected_names: set[str] = set()
        for inp in node_inputs:
            if not isinstance(inp, dict):
                continue
            name = inp.get("name", "")
            link_id = inp.get("link")
            if link_id is not None and link_id in link_map:
                from_node, from_idx = link_map[link_id]
                inputs[name] = [from_node, from_idx]
                connected_names.add(name)

        # Figure out which input NAMES the widget values belong to.
        # Priority:
        #   1. If we have the schema for this class_type, use its ordered list
        #      (ComfyUI's own truth for input order).
        #   2. Otherwise, fall back to the editor node's own 'inputs' array
        #      entries that are unconnected (old behavior — fragile).
        if class_type in node_schema:
            # Widget values fill ALL non-connected inputs in schema order.
            # Connected inputs (from links) are skipped — they already have values.
            ordered_names = [n for n in node_schema[class_type] if n not in connected_names]
        else:
            ordered_names = [
                inp.get("name", "") for inp in node_inputs
                if isinstance(inp, dict) and inp.get("link") is None and inp.get("name") not in connected_names
            ]

        wi = 0
        for name in ordered_names:
            if wi >= len(widgets):
                break
            val = widgets[wi]
            # Skip control widgets (seed mode: randomize/fixed/increment/decrement)
            if isinstance(val, str) and val in _CONTROL_WIDGETS:
                wi += 1
                if wi >= len(widgets):
                    break
                val = widgets[wi]
            inputs[name] = val
            wi += 1
            # After seed inputs, the next value is often a control widget — skip if so
            if name == "seed" and wi < len(widgets) and isinstance(widgets[wi], str) and widgets[wi] in _CONTROL_WIDGETS:
                wi += 1

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
async def get_checkpoints(db: AsyncSession = Depends(get_db)):
    """Query ComfyUI for available checkpoints and UNET models."""
    checkpoints: List[str] = []
    unet_models: List[str] = []

    try:
        comfyui_url = await _get_running_comfyui_url(db, timeout=5.0)
        if not comfyui_url:
            return CheckpointsResponse(checkpoints=[], unet_models=[], status="offline")

        async with httpx.AsyncClient(timeout=5.0) as client:
            # Standard checkpoints
            try:
                r = await client.get(f"{comfyui_url}/object_info/CheckpointLoaderSimple")
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
                r = await client.get(f"{comfyui_url}/object_info/UNETLoader")
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


class ComfyUIEndpointStatus(BaseModel):
    url: str
    status: str  # "online" or "offline"
    queue_running: int
    queue_pending: int
    queue_total: int


class ComfyUIEndpointsResponse(BaseModel):
    data: List[ComfyUIEndpointStatus]
    active_url: Optional[str] = None


@router.get("/comfyui/endpoints", response_model=ComfyUIEndpointsResponse)
async def comfyui_endpoints(db: AsyncSession = Depends(get_db)):
    """Return live health + queue depth for all configured ComfyUI URLs."""
    configured = await get_setting("comfyui_url", db)
    urls = _parse_comfyui_urls(configured)
    results: List[ComfyUIEndpointStatus] = []

    async with httpx.AsyncClient(timeout=3.0) as client:
        for url in urls:
            try:
                stats_resp = await client.get(f"{url}/system_stats")
                if stats_resp.status_code != 200:
                    results.append(
                        ComfyUIEndpointStatus(
                            url=url,
                            status="offline",
                            queue_running=0,
                            queue_pending=0,
                            queue_total=0,
                        )
                    )
                    continue

                running = 0
                pending = 0
                queue_resp = await client.get(f"{url}/queue")
                if queue_resp.status_code == 200:
                    queue_data = queue_resp.json()
                    running = len(queue_data.get("queue_running", []) or [])
                    pending = len(queue_data.get("queue_pending", []) or [])

                results.append(
                    ComfyUIEndpointStatus(
                        url=url,
                        status="online",
                        queue_running=running,
                        queue_pending=pending,
                        queue_total=running + pending,
                    )
                )
            except Exception:
                results.append(
                    ComfyUIEndpointStatus(
                        url=url,
                        status="offline",
                        queue_running=0,
                        queue_pending=0,
                        queue_total=0,
                    )
                )

    online = [r for r in results if r.status == "online"]
    active_url = None
    if online:
        active_url = sorted(online, key=lambda r: (r.queue_total, r.queue_pending, r.queue_running))[0].url

    return ComfyUIEndpointsResponse(data=results, active_url=active_url)


@router.get("/comfyui/loras", response_model=LorasResponse)
async def get_loras(db: AsyncSession = Depends(get_db)):
    """Query ComfyUI for available LoRA models."""
    loras: List[str] = []
    try:
        comfyui_url = await _get_running_comfyui_url(db, timeout=5.0)
        if not comfyui_url:
            return LorasResponse(loras=[], status="offline")

        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{comfyui_url}/object_info/LoraLoader")
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
async def comfyui_status(db: AsyncSession = Depends(get_db)):
    """Check if ComfyUI is running and get system stats."""
    try:
        comfyui_url = await _get_running_comfyui_url(db, timeout=3.0)
        if not comfyui_url:
            return {"status": "offline", "system_stats": None}

        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{comfyui_url}/system_stats")
            if r.status_code == 200:
                stats = r.json()
                return {
                    "status": "online",
                    "url": comfyui_url,
                    "system_stats": stats,
                }
    except Exception:
        pass

    return {"status": "offline", "system_stats": None}
