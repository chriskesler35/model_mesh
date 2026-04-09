"""Agent CRUD + run endpoints for DevForgeAI."""

import json
import uuid
import time
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db, AsyncSessionLocal
from app.models.agent import Agent, DEFAULT_AGENTS
from app.models import Persona, Model
from app.middleware.auth import verify_api_key
from pydantic import BaseModel
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/agents", tags=["agents"], dependencies=[Depends(verify_api_key)])


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _resolve_agent_model(agent: Agent, db: AsyncSession) -> dict:
    """
    Resolve the effective model and system prompt for an agent.

    Model priority:  persona.primary_model → agent.model_id → None
    Prompt strategy: persona.system_prompt is the foundation;
                     agent.system_prompt (if set) is appended as role-specific
                     additional instructions.  If no persona, agent prompt is used alone.
    """
    resolved = {
        "resolved_model_id": None,
        "resolved_model_name": None,
        "resolved_via": None,
        "persona_name": None,
        "persona_system_prompt": None,
        "effective_system_prompt": agent.system_prompt or "",
    }

    # Try persona first
    if agent.persona_id:
        try:
            persona_result = await db.execute(
                select(Persona).where(Persona.id == agent.persona_id)
            )
            persona = persona_result.scalar_one_or_none()
            if persona:
                resolved["persona_name"] = persona.name
                resolved["persona_system_prompt"] = persona.system_prompt or ""

                # Build effective prompt: persona is the base, agent adds role specifics
                parts = [p.strip() for p in [persona.system_prompt or "", agent.system_prompt or ""] if p and p.strip()]
                resolved["effective_system_prompt"] = "\n\n".join(parts)

                if persona.primary_model_id:
                    model_result = await db.execute(
                        select(Model).where(Model.id == persona.primary_model_id)
                    )
                    model = model_result.scalar_one_or_none()
                    if model:
                        resolved["resolved_model_id"] = str(model.id)
                        resolved["resolved_model_name"] = model.display_name or model.model_id
                        resolved["resolved_via"] = "persona"
        except Exception as e:
            logger.warning(f"Failed to resolve persona for agent {agent.id}: {e}")

    # Fall back to direct model_id
    if not resolved["resolved_model_id"] and agent.model_id:
        try:
            model_result = await db.execute(
                select(Model).where(Model.id == agent.model_id)
            )
            model = model_result.scalar_one_or_none()
            if model:
                resolved["resolved_model_id"] = str(model.id)
                resolved["resolved_model_name"] = model.display_name or model.model_id
                resolved["resolved_via"] = "direct"
        except Exception as e:
            logger.warning(f"Failed to resolve direct model for agent {agent.id}: {e}")

    return resolved


def _agent_to_dict(agent: Agent) -> dict:
    """Convert agent ORM object to plain dict."""
    import uuid as _uuid
    from datetime import datetime
    d = {}
    for f in ['id', 'name', 'agent_type', 'description', 'system_prompt',
              'model_id', 'persona_id', 'method_phase', 'tools', 'memory_enabled',
              'max_iterations', 'timeout_seconds', 'is_active', 'created_at', 'updated_at']:
        val = getattr(agent, f, None)
        if isinstance(val, _uuid.UUID):
            val = str(val)
        if isinstance(val, datetime):
            val = val.isoformat()
        d[f] = val
    return d


# ─── Schemas ──────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    agent_type: str
    description: Optional[str] = None
    system_prompt: str
    model_id: Optional[str] = None
    persona_id: Optional[str] = None
    method_phase: Optional[str] = None
    tools: List[str] = []
    memory_enabled: bool = True
    max_iterations: int = 10
    timeout_seconds: int = 300


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    agent_type: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_id: Optional[str] = None
    persona_id: Optional[str] = None
    method_phase: Optional[str] = None
    tools: Optional[List[str]] = None
    memory_enabled: Optional[bool] = None
    max_iterations: Optional[int] = None
    timeout_seconds: Optional[int] = None
    is_active: Optional[bool] = None


class AgentResponse(BaseModel):
    id: str
    name: str
    agent_type: str
    description: Optional[str] = None
    system_prompt: str
    model_id: Optional[str] = None
    persona_id: Optional[str] = None
    persona_name: Optional[str] = None
    persona_system_prompt: Optional[str] = None   # persona's own prompt, for UI display
    effective_system_prompt: Optional[str] = None # merged prompt used at runtime
    resolved_model_id: Optional[str] = None
    resolved_model_name: Optional[str] = None
    resolved_via: Optional[str] = None  # "persona" | "direct" | None
    method_phase: Optional[str] = None
    tools: List[str] = []
    memory_enabled: bool = True
    max_iterations: int = 10
    timeout_seconds: int = 300
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class AgentListResponse(BaseModel):
    data: List[AgentResponse]
    total: int


class AgentRunRequest(BaseModel):
    task: str
    context: Optional[dict] = None
    stream: Optional[bool] = False


class AgentRunResponse(BaseModel):
    run_id: str
    agent_id: str
    status: str  # "completed", "failed", "timeout"
    output: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/method-phases")
async def list_method_phases():
    """List all unique phase names across every development method.

    Returns one entry per phase name with the role, methods it appears in,
    and the bound agent (if any). The frontend uses this to show which phase
    slots exist and which don't have an agent assigned yet.
    """
    from app.services.phase_templates import METHOD_PHASE_TEMPLATES
    # Collect unique phase names + which methods use them + role
    phase_info: Dict[str, dict] = {}
    for method_id, phases in METHOD_PHASE_TEMPLATES.items():
        for ph in phases:
            name = ph["name"]
            if name not in phase_info:
                phase_info[name] = {
                    "name": name,
                    "role": ph["role"],
                    "methods": [],
                    "default_model": ph.get("default_model"),
                }
            phase_info[name]["methods"].append(method_id)
    return {"data": list(phase_info.values())}


@router.get("", response_model=AgentListResponse)
async def list_agents(
    agent_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    query = select(Agent)
    if agent_type:
        query = query.where(Agent.agent_type == agent_type)
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    agents = result.scalars().all()

    if not agents:
        # Return defaults with no model resolution
        defaults = []
        for d in DEFAULT_AGENTS:
            defaults.append(AgentResponse(
                id=f"default-{d['agent_type']}",
                name=d["name"], agent_type=d["agent_type"],
                description=d.get("description"), system_prompt=d["system_prompt"],
                tools=d.get("tools", []),
                max_iterations=d.get("max_iterations", 10),
                timeout_seconds=d.get("timeout_seconds", 300),
                created_at="default", updated_at="default"
            ))
        return AgentListResponse(data=defaults, total=len(defaults))

    data = []
    for agent in agents:
        d = _agent_to_dict(agent)
        resolved = await _resolve_agent_model(agent, db)
        d.update(resolved)
        data.append(AgentResponse(**d))

    return AgentListResponse(data=data, total=len(data))


@router.post("", response_model=AgentResponse)
async def create_agent(agent: AgentCreate, db: AsyncSession = Depends(get_db)):
    from app.models import UserProfile
    result = await db.execute(select(UserProfile).limit(1))
    user = result.scalar_one_or_none()

    new_agent = Agent(
        id=uuid.uuid4(),
        name=agent.name,
        agent_type=agent.agent_type,
        description=agent.description,
        system_prompt=agent.system_prompt,
        model_id=uuid.UUID(agent.model_id) if agent.model_id else None,
        persona_id=uuid.UUID(agent.persona_id) if agent.persona_id else None,
        tools=agent.tools,
        memory_enabled=agent.memory_enabled,
        max_iterations=agent.max_iterations,
        timeout_seconds=agent.timeout_seconds,
        user_id=user.id if user else None
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)

    d = _agent_to_dict(new_agent)
    resolved = await _resolve_agent_model(new_agent, db)
    d.update(resolved)
    return AgentResponse(**d)


@router.get("/defaults", response_model=AgentListResponse)
async def get_default_agents():
    agents = [AgentResponse(
        id=str(uuid.uuid4()), name=d["name"], agent_type=d["agent_type"],
        description=d.get("description"), system_prompt=d["system_prompt"],
        tools=d.get("tools", []), max_iterations=d.get("max_iterations", 10),
        timeout_seconds=d.get("timeout_seconds", 300), created_at="", updated_at=""
    ) for d in DEFAULT_AGENTS]
    return AgentListResponse(data=agents, total=len(agents))


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    # Handle default-* IDs (hardcoded agents not yet saved to DB)
    if agent_id.startswith("default-"):
        agent_type = agent_id[len("default-"):]
        for d in DEFAULT_AGENTS:
            if d["agent_type"] == agent_type:
                return AgentResponse(
                    id=agent_id,
                    name=d["name"],
                    agent_type=d["agent_type"],
                    description=d.get("description"),
                    system_prompt=d["system_prompt"],
                    tools=d.get("tools", []),
                    max_iterations=d.get("max_iterations", 10),
                    timeout_seconds=d.get("timeout_seconds", 300),
                    memory_enabled=True,
                    is_active=True,
                    created_at="default",
                    updated_at="default"
                )
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    except ValueError:
        result = await db.execute(select(Agent).where(Agent.name == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    d = _agent_to_dict(agent)
    resolved = await _resolve_agent_model(agent, db)
    d.update(resolved)
    return AgentResponse(**d)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, updates: AgentUpdate, db: AsyncSession = Depends(get_db)):
    # If editing a default agent, promote it to a real DB record first
    if agent_id.startswith("default-"):
        agent_type = agent_id[len("default-"):]
        default_data = next((d for d in DEFAULT_AGENTS if d["agent_type"] == agent_type), None)
        if not default_data:
            raise HTTPException(status_code=404, detail="Agent not found")

        from app.models import UserProfile
        user_result = await db.execute(select(UserProfile).limit(1))
        user = user_result.scalar_one_or_none()

        agent = Agent(
            id=uuid.uuid4(),
            name=updates.name or default_data["name"],
            agent_type=updates.agent_type or default_data["agent_type"],
            description=updates.description if updates.description is not None else default_data.get("description"),
            system_prompt=updates.system_prompt or default_data["system_prompt"],
            tools=updates.tools if updates.tools is not None else default_data.get("tools", []),
            memory_enabled=updates.memory_enabled if updates.memory_enabled is not None else True,
            max_iterations=updates.max_iterations or default_data.get("max_iterations", 10),
            timeout_seconds=updates.timeout_seconds or default_data.get("timeout_seconds", 300),
            is_active=True,
            user_id=user.id if user else None,
            model_id=uuid.UUID(updates.model_id) if updates.model_id else None,
            persona_id=uuid.UUID(updates.persona_id) if updates.persona_id else None,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        d = _agent_to_dict(agent)
        resolved = await _resolve_agent_model(agent, db)
        d.update(resolved)
        return AgentResponse(**d)

    try:
        result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    except ValueError:
        result = await db.execute(select(Agent).where(Agent.name == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    for field in ['name', 'agent_type', 'description', 'system_prompt',
                  'tools', 'memory_enabled', 'max_iterations', 'timeout_seconds', 'is_active']:
        val = getattr(updates, field, None)
        if val is not None:
            setattr(agent, field, val)

    if updates.model_id is not None:
        agent.model_id = uuid.UUID(updates.model_id) if updates.model_id else None
    if updates.persona_id is not None:
        agent.persona_id = uuid.UUID(updates.persona_id) if updates.persona_id else None

    await db.commit()
    await db.refresh(agent)
    d = _agent_to_dict(agent)
    resolved = await _resolve_agent_model(agent, db)
    d.update(resolved)
    return AgentResponse(**d)


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    except ValueError:
        result = await db.execute(select(Agent).where(Agent.name == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()
    return {"status": "deleted"}


# ─── Run schemas ─────────────────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    task: str
    context: Optional[dict] = None
    stream: bool = False
    model_id: Optional[str] = None  # Override agent's model


# ─── Run endpoint ────────────────────────────────────────────────────────────

async def _resolve_model_for_run(model_id: str):
    """Resolve (Model, Provider) ORM objects for a model_id string.

    Reuses the same pattern as workbench._resolve_model but avoids a
    cross-module import so agents.py stays self-contained.
    """
    from app.database import AsyncSessionLocal
    from app.models.model import Model as ModelORM
    from app.models.provider import Provider as ProviderORM
    from app.services.provider_credentials import has_provider_api_key

    async with AsyncSessionLocal() as db:
        # Exact match
        result = await db.execute(
            select(ModelORM, ProviderORM)
            .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
            .where(ModelORM.model_id == model_id)
            .limit(1)
        )
        row = result.first()
        if row:
            if not has_provider_api_key(row[1].name):
                logger.error(
                    "Model '%s' matched but provider '%s' has no credentials",
                    model_id, row[1].name,
                )
                return None, None
            return row[0], row[1]

        # Fuzzy partial match
        last_part = model_id.split("/")[-1]
        result = await db.execute(
            select(ModelORM, ProviderORM)
            .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
            .where(ModelORM.model_id.contains(last_part))
            .where(ModelORM.is_active == True)
        )
        for m, p in result:
            if has_provider_api_key(p.name):
                logger.info(
                    "Model '%s' fuzzy-matched to '%s' via %s",
                    model_id, m.model_id, p.name,
                )
                return m, p

        logger.error("Could not resolve model '%s'", model_id)
    return None, None


async def _resolve_agent_model_id(agent, db: AsyncSession) -> Optional[str]:
    """Get the effective model_id string for an agent (persona → direct → None)."""
    # Try persona's primary model first
    if agent.persona_id:
        try:
            persona_result = await db.execute(
                select(Persona).where(Persona.id == agent.persona_id)
            )
            persona = persona_result.scalar_one_or_none()
            if persona and persona.primary_model_id:
                model_result = await db.execute(
                    select(Model).where(Model.id == persona.primary_model_id)
                )
                model = model_result.scalar_one_or_none()
                if model:
                    return model.model_id
        except Exception as e:
            logger.warning("Persona model resolution failed: %s", e)

    # Direct model_id
    if agent.model_id:
        try:
            model_result = await db.execute(
                select(Model).where(Model.id == agent.model_id)
            )
            model = model_result.scalar_one_or_none()
            if model:
                return model.model_id
        except Exception as e:
            logger.warning("Direct model resolution failed: %s", e)

    return None


@router.post("/{agent_id}/run")
async def run_agent(agent_id: str, body: AgentRunRequest, db: AsyncSession = Depends(get_db)):
    """Execute an agent's task with iterative tool loop.

    If the agent has tools configured, uses AgentRunner for multi-iteration
    tool execution.  Otherwise falls back to a single LLM call.

    Supports both streaming (SSE) and synchronous responses via body.stream.
    """
    from app.services.agent_runner import AgentRunner

    # ── Look up agent ────────────────────────────────────────────────────
    agent = None
    default_data = None

    if agent_id.startswith("default-"):
        agent_type = agent_id[len("default-"):]
        default_data = next(
            (d for d in DEFAULT_AGENTS if d["agent_type"] == agent_type), None
        )
        if not default_data:
            raise HTTPException(status_code=404, detail="Agent not found")
    else:
        try:
            result = await db.execute(
                select(Agent).where(Agent.id == uuid.UUID(agent_id))
            )
        except ValueError:
            result = await db.execute(
                select(Agent).where(Agent.name == agent_id)
            )
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

    # ── Resolve model ────────────────────────────────────────────────────
    # Priority: body.model_id → agent model → fallback
    if body.model_id:
        effective_model_id = body.model_id
    elif agent:
        effective_model_id = await _resolve_agent_model_id(agent, db)
    else:
        effective_model_id = None

    if not effective_model_id:
        # Use a sensible default
        effective_model_id = "claude-sonnet-4-6"

    model_orm, provider_orm = await _resolve_model_for_run(effective_model_id)
    if not model_orm:
        raise HTTPException(
            status_code=400,
            detail=f"Could not resolve model '{effective_model_id}'. "
            "Ensure the model exists and its provider has credentials configured.",
        )

    # ── Build a lightweight agent-like object for defaults ───────────────
    if default_data and not agent:
        # Create a simple namespace so AgentRunner can use getattr
        class _DefaultAgent:
            pass
        agent = _DefaultAgent()
        agent.system_prompt = default_data["system_prompt"]
        agent.tools = default_data.get("tools", [])
        agent.max_iterations = default_data.get("max_iterations", 10)
        agent.timeout_seconds = default_data.get("timeout_seconds", 300)

    agent_tools = getattr(agent, "tools", []) or []

    # ── Single-shot (no tools) ───────────────────────────────────────────
    if not agent_tools:
        from app.services.model_client import ModelClient

        client = ModelClient()
        system_prompt = getattr(agent, "system_prompt", "") or ""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": body.task},
        ]
        if body.context:
            messages[-1]["content"] += (
                f"\n\nAdditional context:\n{json.dumps(body.context, indent=2)}"
            )

        if body.stream:
            async def _single_shot_stream():
                try:
                    stream = await client.call_model(
                        model=model_orm,
                        provider=provider_orm,
                        messages=messages,
                        stream=True,
                        temperature=0.2,
                        max_tokens=8000,
                    )
                    async for chunk in stream:
                        delta = ""
                        try:
                            if hasattr(chunk, "choices") and chunk.choices:
                                delta = chunk.choices[0].delta.content or ""
                        except Exception:
                            pass
                        if delta:
                            yield f"data: {json.dumps({'event': 'chunk', 'data': delta})}\n\n"
                    yield f"data: {json.dumps({'event': 'done'})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                _single_shot_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        # Synchronous single-shot
        try:
            response = await client.call_model(
                model=model_orm,
                provider=provider_orm,
                messages=messages,
                stream=False,
                temperature=0.2,
                max_tokens=8000,
            )
            content = ""
            if hasattr(response, "choices") and response.choices:
                content = response.choices[0].message.content or ""
            return {
                "run_id": str(uuid.uuid4()),
                "status": "completed",
                "output": content,
                "iterations": [],
                "iteration_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "duration_ms": 0,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Multi-iteration tool loop ────────────────────────────────────────
    runner = AgentRunner(agent, model_orm, provider_orm)

    if body.stream:
        async def _stream_runner():
            try:
                async for event in runner.run_stream(body.task, body.context):
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(
            _stream_runner(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # Synchronous run
    try:
        result = await runner.run(body.task, body.context)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
