"""BMAD Method Integration — development methodology selection and injection."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import verify_api_key
from app.models.custom_method import CustomMethod

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/methods", tags=["methods"], dependencies=[Depends(verify_api_key)])

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_METHODS_STATE = _DATA_DIR / "methods_state.json"

# ─── Built-in methods ─────────────────────────────────────────────────────────
BUILT_IN_METHODS: Dict[str, Dict[str, Any]] = {
    "standard": {
        "id": "standard",
        "name": "Standard",
        "tagline": "Default assistant behavior",
        "icon": "💬",
        "color": "gray",
        "description": "No special methodology applied. The AI responds naturally based on the active persona and soul.",
        "system_prompt": "",
        "phases": [],
        "settings": {},
    },
    "bmad": {
        "id": "bmad",
        "name": "BMAD",
        "tagline": "Brainstorm → Model → Architect → Deploy",
        "icon": "🧠",
        "color": "purple",
        "description": "Structured methodology for complex projects. Forces deliberate thinking through four phases before writing a single line of code.",
        "system_prompt": """# BMAD Method Active

You are operating under the BMAD (Brainstorm → Model → Architect → Deploy) methodology. Apply this framework to all development tasks:

## Phase 1: BRAINSTORM
Before anything else, explore the problem space. Ask clarifying questions. Surface assumptions. Consider edge cases and alternative approaches. Do NOT jump to solutions yet.

## Phase 2: MODEL
Define the data model, API contracts, and component interfaces. Write these out explicitly before implementation. Agree on the shape of things before building them.

## Phase 3: ARCHITECT
Design the system structure. File layout, dependencies, patterns, error handling strategy. Produce a concise technical spec or plan. Get sign-off before coding.

## Phase 4: DEPLOY
Now implement — following the plan. Flag any deviations. Test as you go. Document what was built.

**Current behavior:** Always state which phase you're in. Refuse to skip phases unless the user explicitly says "skip to [phase]". Keep responses focused and structured.""",
        "phases": ["Brainstorm", "Model", "Architect", "Deploy"],
        "settings": {
            "require_phase_confirmation": True,
            "auto_advance_phases": False,
        },
    },
    "gsd": {
        "id": "gsd",
        "name": "GSD",
        "tagline": "Get Shit Done — rapid prototyping mode",
        "icon": "⚡",
        "color": "orange",
        "description": "Move fast. Minimal ceremony. Ship working code quickly, iterate from there. Best for prototypes, experiments, and small tasks.",
        "system_prompt": """# GSD Mode Active — Get Shit Done

You are in rapid prototyping mode. Priorities in order:
1. **Working code > perfect code** — Ship something that runs, then improve it
2. **Bias to action** — When in doubt, make a reasonable assumption and go. Note assumptions briefly.
3. **No over-engineering** — Use the simplest solution that works. No premature abstraction.
4. **Skip the preamble** — Don't explain what you're about to do. Just do it.
5. **Inline TODO > blocking** — If something is complex, leave a clear TODO and keep moving.

Output working, runnable code. If you need to ask something, ask ONE question maximum.""",
        "phases": [],
        "settings": {
            "skip_confirmation": True,
            "prefer_inline_todos": True,
        },
    },
    "superpowers": {
        "id": "superpowers",
        "name": "SuperPowers",
        "tagline": "Structured prompting for complex multi-step tasks",
        "icon": "🦸",
        "color": "blue",
        "description": "Deep research and analysis mode. Breaks complex tasks into parallel workstreams, synthesizes findings, produces comprehensive outputs.",
        "system_prompt": """# SuperPowers Mode Active

You are operating in structured deep-work mode for complex tasks. Apply this framework:

## Approach
1. **Decompose** — Break the task into independent sub-problems
2. **Parallelize** — Identify what can be worked simultaneously vs sequentially
3. **Research first** — Gather context before proposing solutions
4. **Synthesize** — Connect findings across sub-problems into coherent output
5. **Validate** — Check your own work against the original requirements

## Output standards
- Be explicit about your reasoning
- Show your work — don't just give answers, show how you got there
- Flag uncertainty clearly: "I'm confident about X, less sure about Y"
- Produce actionable, structured outputs (not walls of prose)

## When stuck
Describe what you know, what you don't know, and what information would unblock you.""",
        "phases": ["Decompose", "Research", "Synthesize", "Validate"],
        "settings": {
            "show_reasoning": True,
            "structured_output": True,
        },
    },
    "gtrack": {
        "id": "gtrack",
        "name": "GTrack",
        "tagline": "Git-based progress tracking",
        "icon": "📊",
        "color": "green",
        "description": "Every significant change gets a commit. Progress is tracked through git history. The AI commits early and often with meaningful messages.",
        "system_prompt": """# GTrack Mode Active — Git-Based Progress Tracking

You are in git-tracked development mode. Rules:
1. **Commit after every meaningful change** — Don't batch unrelated changes
2. **Meaningful commit messages** — Format: `type: brief description` (feat/fix/refactor/docs/test)
3. **Branch per feature** — Never commit directly to main for new features
4. **Progress = commits** — Each commit is a checkpoint. Treat them as save points.
5. **Before starting** — Check git status. Know what branch you're on.
6. **After finishing** — Summarize what was committed and what's left.

Always include git commands in your implementation steps.""",
        "phases": [],
        "settings": {
            "auto_commit": True,
            "require_branch": True,
        },
    },
}


# ─── State helpers ────────────────────────────────────────────────────────────
def _load_state() -> Dict[str, Any]:
    if _METHODS_STATE.exists():
        try:
            return json.loads(_METHODS_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"active_method": "standard", "active_stack": [], "method_settings": {}}


def _save_state(state: Dict[str, Any]):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _METHODS_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# Conflicting method pairs — warn but don't block
CONFLICTS = [
    {"bmad", "gsd"},  # structured vs. ship-fast
]

def _build_stack_prompt(stack: List[str]) -> str:
    """Concatenate prompts from all stacked methods in order."""
    parts = []
    for mid in stack:
        m = BUILT_IN_METHODS.get(mid)
        if m and m.get("system_prompt"):
            parts.append(m["system_prompt"])
    return "\n\n---\n\n".join(parts)

def _check_conflicts(stack: List[str]) -> List[str]:
    warnings = []
    stack_set = set(stack)
    for pair in CONFLICTS:
        if pair.issubset(stack_set):
            warnings.append(f"⚠️ Conflicting methods: {' + '.join(pair)} — these have opposing priorities")
    return warnings


# ─── Models ───────────────────────────────────────────────────────────────────
class MethodActivate(BaseModel):
    method_id: str

class StackUpdate(BaseModel):
    stack: List[str]  # ordered list of method ids

class MethodSettingsUpdate(BaseModel):
    settings: Dict[str, Any]

class MethodImportPayload(BaseModel):
    """Schema for the inner 'method' object in an import request."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    phases: List[Dict[str, Any]]
    trigger_keywords: Optional[List[str]] = None
    category: Optional[str] = None

class MethodImportRequest(BaseModel):
    """Top-level import request body."""
    version: str
    method: MethodImportPayload


# ─── Routes ───────────────────────────────────────────────────────────────────
@router.get("/")
async def list_methods(db: AsyncSession = Depends(get_db)):
    state = _load_state()
    active = state.get("active_method", "standard")
    stack = state.get("active_stack", [])
    data = []
    for m in BUILT_IN_METHODS.values():
        entry = dict(m)
        entry["is_active"] = (m["id"] == active)
        entry["in_stack"] = m["id"] in stack
        entry["stack_position"] = stack.index(m["id"]) + 1 if m["id"] in stack else None
        entry["is_custom"] = False
        data.append(entry)

    # Include custom methods from the database
    result = await db.execute(
        select(CustomMethod).where(CustomMethod.is_active == True)
    )
    custom_methods = result.scalars().all()
    for cm in custom_methods:
        entry = {
            "id": cm.id,
            "name": cm.name,
            "tagline": cm.description or "",
            "icon": "",
            "color": "teal",
            "description": cm.description or "",
            "system_prompt": "",
            "phases": [p.get("name", "") for p in (cm.phases or [])],
            "settings": {},
            "trigger_keywords": cm.trigger_keywords or [],
            "is_active": (cm.id == active),
            "in_stack": cm.id in stack,
            "stack_position": stack.index(cm.id) + 1 if cm.id in stack else None,
            "is_custom": True,
        }
        data.append(entry)

    return {
        "data": data,
        "active_method": active,
        "active_stack": stack,
        "stack_mode": len(stack) > 1,
        "conflicts": _check_conflicts(stack),
    }


@router.get("/active")
async def get_active_method():
    state = _load_state()
    stack = state.get("active_stack", [])
    if len(stack) > 1:
        # Stack mode — return a synthetic combined method
        names = [BUILT_IN_METHODS[mid]["name"] for mid in stack if mid in BUILT_IN_METHODS]
        return {
            "id": "stack",
            "name": " + ".join(names),
            "tagline": "Method stack active",
            "icon": "🔀",
            "color": "purple",
            "is_active": True,
            "stack": stack,
            "system_prompt": _build_stack_prompt(stack),
        }
    active_id = state.get("active_method", "standard")
    method = BUILT_IN_METHODS.get(active_id, BUILT_IN_METHODS["standard"])
    return {**method, "is_active": True, "stack": [active_id] if active_id != "standard" else []}


@router.get("/active/prompt")
async def get_active_prompt():
    """Returns the combined system prompt for injection into chat."""
    state = _load_state()
    stack = state.get("active_stack", [])
    if len(stack) > 1:
        prompt = _build_stack_prompt(stack)
        return {"method_id": "stack", "stack": stack, "prompt": prompt}
    active_id = state.get("active_method", "standard")
    method = BUILT_IN_METHODS.get(active_id, BUILT_IN_METHODS["standard"])
    return {"method_id": active_id, "stack": [], "prompt": method.get("system_prompt", "")}


@router.post("/activate")
async def activate_method(body: MethodActivate):
    """Activate a single method (clears stack mode)."""
    if body.method_id not in BUILT_IN_METHODS:
        raise HTTPException(status_code=404, detail=f"Method '{body.method_id}' not found")
    state = _load_state()
    state["active_method"] = body.method_id
    state["active_stack"] = [body.method_id] if body.method_id != "standard" else []
    _save_state(state)
    return {"ok": True, "active_method": body.method_id, "active_stack": state["active_stack"]}


@router.post("/stack")
async def set_stack(body: StackUpdate):
    """Set the active method stack (2+ methods run together)."""
    invalid = [mid for mid in body.stack if mid not in BUILT_IN_METHODS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown methods: {invalid}")
    # Remove 'standard' from stacks — it's a no-op
    clean_stack = [mid for mid in body.stack if mid != "standard"]
    state = _load_state()
    state["active_stack"] = clean_stack
    state["active_method"] = clean_stack[0] if clean_stack else "standard"
    _save_state(state)
    warnings = _check_conflicts(clean_stack)
    return {
        "ok": True,
        "active_stack": clean_stack,
        "stack_mode": len(clean_stack) > 1,
        "conflicts": warnings,
    }


@router.post("/stack/add")
async def add_to_stack(body: MethodActivate):
    """Add a method to the current stack."""
    if body.method_id not in BUILT_IN_METHODS or body.method_id == "standard":
        raise HTTPException(status_code=400, detail="Cannot add this method to a stack")
    state = _load_state()
    stack = state.get("active_stack", [])
    if body.method_id not in stack:
        stack.append(body.method_id)
    state["active_stack"] = stack
    state["active_method"] = stack[0] if stack else "standard"
    _save_state(state)
    warnings = _check_conflicts(stack)
    return {"ok": True, "active_stack": stack, "conflicts": warnings}


@router.post("/stack/remove")
async def remove_from_stack(body: MethodActivate):
    """Remove a method from the stack."""
    state = _load_state()
    stack = [mid for mid in state.get("active_stack", []) if mid != body.method_id]
    state["active_stack"] = stack
    state["active_method"] = stack[0] if stack else "standard"
    _save_state(state)
    return {"ok": True, "active_stack": stack}


@router.delete("/stack")
async def clear_stack():
    """Clear the stack and reset to Standard."""
    state = _load_state()
    state["active_stack"] = []
    state["active_method"] = "standard"
    _save_state(state)
    return {"ok": True, "active_stack": []}


# ─── Import / Export ──────────────────────────────────────────────────────────

@router.get("/custom/{method_id}/export")
async def export_custom_method(method_id: str, db: AsyncSession = Depends(get_db)):
    """Export a custom method as downloadable JSON."""
    result = await db.execute(
        select(CustomMethod).where(CustomMethod.id == method_id)
    )
    cm = result.scalar_one_or_none()
    if not cm:
        raise HTTPException(status_code=404, detail="Custom method not found")

    export_data = {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "name": cm.name,
            "description": cm.description,
            "phases": cm.phases or [],
            "trigger_keywords": cm.trigger_keywords or [],
            "category": "custom",
        },
    }
    filename = cm.name.replace(" ", "_").lower() + ".json"
    return JSONResponse(
        content=export_data,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/custom/import")
async def import_custom_method(body: MethodImportRequest, db: AsyncSession = Depends(get_db)):
    """Import a custom method from JSON. Warns if a method with the same name exists."""
    method_data = body.method

    # Duplicate detection
    existing = await db.execute(
        select(CustomMethod).where(CustomMethod.name == method_data.name)
    )
    duplicate = existing.scalar_one_or_none()
    warning = None
    if duplicate:
        warning = f"A method named '{method_data.name}' already exists (id={duplicate.id}). A new copy was created."

    new_method = CustomMethod(
        name=method_data.name if not duplicate else f"{method_data.name} (imported)",
        description=method_data.description,
        phases=method_data.phases,
        trigger_keywords=method_data.trigger_keywords or [],
        is_active=True,
    )
    db.add(new_method)
    await db.commit()
    await db.refresh(new_method)

    result = {"ok": True, "method": new_method.to_dict()}
    if warning:
        result["warning"] = warning
    return result


@router.get("/{method_id}")
async def get_method(method_id: str, db: AsyncSession = Depends(get_db)):
    state = _load_state()
    stack = state.get("active_stack", [])

    # Check built-in methods first
    if method_id in BUILT_IN_METHODS:
        m = dict(BUILT_IN_METHODS[method_id])
        m["is_active"] = (state.get("active_method") == method_id)
        m["in_stack"] = method_id in stack
        m["stack_position"] = stack.index(method_id) + 1 if method_id in stack else None
        m["is_custom"] = False
        return m

    # Check custom methods by ID
    result = await db.execute(
        select(CustomMethod).where(CustomMethod.id == method_id)
    )
    cm = result.scalar_one_or_none()
    if cm:
        return {
            "id": cm.id,
            "name": cm.name,
            "tagline": cm.description or "",
            "icon": "",
            "color": "teal",
            "description": cm.description or "",
            "system_prompt": "",
            "phases": [p.get("name", "") for p in (cm.phases or [])],
            "settings": {},
            "trigger_keywords": cm.trigger_keywords or [],
            "is_active": (cm.id == state.get("active_method")),
            "in_stack": cm.id in stack,
            "stack_position": stack.index(cm.id) + 1 if cm.id in stack else None,
            "is_custom": True,
        }

    raise HTTPException(status_code=404, detail="Method not found")
