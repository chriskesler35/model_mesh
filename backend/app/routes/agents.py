"""Agent CRUD endpoints for DevForgeAI."""

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


# ─── Agent Run ───────────────────────────────────────────────────────────────


async def _resolve_model_for_run(model_id: str):
    """Resolve Model + Provider ORM objects from a model UUID string.

    Re-uses the same resolution logic as pipeline phase execution.
    Returns (Model, Provider) or (None, None) if not found / no credentials.
    """
    from app.routes.workbench import _resolve_model
    return await _resolve_model(model_id)


async def _execute_agent_llm(
    agent: Agent,
    resolved: dict,
    task: str,
    context: Optional[dict],
    run_id: str,
) -> Dict[str, Any]:
    """Run the LLM call for an agent and return result dict.

    This is the core execution function shared by both streaming and
    non-streaming paths (non-streaming collects the full response;
    streaming yields chunks then finalises).
    """
    from app.services.model_client import ModelClient

    model_id = resolved["resolved_model_id"]
    if not model_id:
        return {
            "run_id": run_id,
            "status": "failed",
            "output": "No model resolved for this agent. Assign a model directly or via a persona.",
            "input_tokens": 0,
            "output_tokens": 0,
            "duration_ms": 0,
        }

    model_orm, provider_orm = await _resolve_model_for_run(model_id)
    if not model_orm or not provider_orm:
        return {
            "run_id": run_id,
            "status": "failed",
            "output": (
                f"Could not resolve model '{model_id}'. "
                "The model may not exist or its provider has no API key configured."
            ),
            "input_tokens": 0,
            "output_tokens": 0,
            "duration_ms": 0,
        }

    # Build messages
    system_prompt = resolved.get("effective_system_prompt") or agent.system_prompt or ""
    user_message = task
    if context:
        user_message = f"{task}\n\n# Additional context\n```json\n{json.dumps(context, indent=2)}\n```"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    client = ModelClient()
    full_response = ""
    input_tokens = 0
    output_tokens = 0
    llm_success = True
    llm_error = None
    started = time.time()

    try:
        stream = await client.call_model(
            model=model_orm,
            provider=provider_orm,
            messages=messages,
            stream=True,
            temperature=0.3,
            max_tokens=16000,
        )

        async for chunk in stream:
            delta = ""
            try:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta.content or ""
                elif isinstance(chunk, dict):
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            except Exception:
                pass

            # Extract token usage from streaming chunks (provider-dependent)
            try:
                usage = None
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = chunk.usage
                elif isinstance(chunk, dict) and chunk.get("usage"):
                    usage = chunk["usage"]
                if usage:
                    input_tokens = (
                        getattr(usage, "prompt_tokens", 0)
                        or (usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0)
                    )
                    output_tokens = (
                        getattr(usage, "completion_tokens", 0)
                        or (usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0)
                    )
            except Exception:
                pass

            if delta:
                full_response += delta

    except Exception as e:
        logger.error(f"LLM call failed for agent run {run_id}: {e}")
        llm_success = False
        llm_error = str(e)

    duration_ms = int((time.time() - started) * 1000)

    # Estimate tokens if the provider didn't report them
    if input_tokens == 0:
        input_tokens = client.estimate_tokens(messages, model_orm)
    if output_tokens == 0 and full_response:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            output_tokens = len(enc.encode(full_response))
        except Exception:
            output_tokens = len(full_response) // 4

    # Write request_log for cost tracking
    try:
        from app.models.request_log import RequestLog
        estimated_cost = client.estimate_cost(input_tokens, output_tokens, model_orm)
        async with AsyncSessionLocal() as db:
            log = RequestLog(
                model_id=str(model_orm.id),
                provider_id=str(provider_orm.id),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=duration_ms,
                estimated_cost=estimated_cost,
                success=llm_success,
                error_message=llm_error,
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        logger.warning(f"request_log write failed for agent run {run_id}: {e}")

    return {
        "run_id": run_id,
        "status": "completed" if llm_success else "failed",
        "output": full_response if llm_success else (llm_error or "Unknown error"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
    }


async def _stream_agent_run(
    agent: Agent,
    resolved: dict,
    task: str,
    context: Optional[dict],
    run_id: str,
    agent_id: str,
) -> AsyncGenerator[str, None]:
    """SSE generator for streaming agent run output.

    Emits events:
      - data: {"type": "chunk", "content": "..."}
      - data: {"type": "done", ...full AgentRunResponse...}
      - data: {"type": "error", "message": "..."}
    """
    from app.services.model_client import ModelClient

    model_id = resolved["resolved_model_id"]
    if not model_id:
        yield f"data: {json.dumps({'type': 'error', 'message': 'No model resolved for this agent.'})}\n\n"
        return

    model_orm, provider_orm = await _resolve_model_for_run(model_id)
    if not model_orm or not provider_orm:
        yield f"data: {json.dumps({'type': 'error', 'message': f'Could not resolve model {model_id}.'})}\n\n"
        return

    system_prompt = resolved.get("effective_system_prompt") or agent.system_prompt or ""
    user_message = task
    if context:
        user_message = f"{task}\n\n# Additional context\n```json\n{json.dumps(context, indent=2)}\n```"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    client = ModelClient()
    full_response = ""
    input_tokens = 0
    output_tokens = 0
    llm_success = True
    llm_error = None
    started = time.time()

    try:
        stream = await client.call_model(
            model=model_orm,
            provider=provider_orm,
            messages=messages,
            stream=True,
            temperature=0.3,
            max_tokens=16000,
        )

        async for chunk in stream:
            delta = ""
            try:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta.content or ""
                elif isinstance(chunk, dict):
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            except Exception:
                pass

            try:
                usage = None
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = chunk.usage
                elif isinstance(chunk, dict) and chunk.get("usage"):
                    usage = chunk["usage"]
                if usage:
                    input_tokens = (
                        getattr(usage, "prompt_tokens", 0)
                        or (usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0)
                    )
                    output_tokens = (
                        getattr(usage, "completion_tokens", 0)
                        or (usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0)
                    )
            except Exception:
                pass

            if delta:
                full_response += delta
                yield f"data: {json.dumps({'type': 'chunk', 'content': delta})}\n\n"

    except Exception as e:
        logger.error(f"LLM streaming call failed for agent run {run_id}: {e}")
        llm_success = False
        llm_error = str(e)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    duration_ms = int((time.time() - started) * 1000)

    # Estimate tokens if the provider didn't report them
    if input_tokens == 0:
        input_tokens = client.estimate_tokens(messages, model_orm)
    if output_tokens == 0 and full_response:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            output_tokens = len(enc.encode(full_response))
        except Exception:
            output_tokens = len(full_response) // 4

    # Write request_log for cost tracking
    try:
        from app.models.request_log import RequestLog
        estimated_cost = client.estimate_cost(input_tokens, output_tokens, model_orm)
        async with AsyncSessionLocal() as db:
            log = RequestLog(
                model_id=str(model_orm.id),
                provider_id=str(provider_orm.id),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=duration_ms,
                estimated_cost=estimated_cost,
                success=llm_success,
                error_message=llm_error,
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        logger.warning(f"request_log write failed for agent run {run_id}: {e}")

    # Final "done" event with full result payload
    done_payload = {
        "type": "done",
        "run_id": run_id,
        "agent_id": agent_id,
        "status": "completed" if llm_success else "failed",
        "output": full_response if llm_success else (llm_error or "Unknown error"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
    }
    yield f"data: {json.dumps(done_payload)}\n\n"


@router.post("/{agent_id}/run", response_model=AgentRunResponse)
async def run_agent(
    agent_id: str,
    body: AgentRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Execute a single agent directly with a task.

    Resolves the agent's model (via persona or direct assignment), calls the
    LLM, logs the request for cost tracking, and returns the result.

    If ``stream: true`` is set in the request body, returns an SSE event
    stream instead of a JSON response.
    """
    # Validate task is non-empty
    if not body.task or not body.task.strip():
        raise HTTPException(status_code=422, detail="Task must not be empty")

    # Look up agent (same pattern as GET /{agent_id})
    agent: Optional[Agent] = None
    if agent_id.startswith("default-"):
        raise HTTPException(
            status_code=422,
            detail="Cannot run a default agent template. Create an agent first (POST /v1/agents).",
        )

    try:
        result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    except ValueError:
        result = await db.execute(select(Agent).where(Agent.name == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Resolve model + effective system prompt
    resolved = await _resolve_agent_model(agent, db)

    run_id = str(uuid.uuid4())

    # Streaming path
    if body.stream:
        return StreamingResponse(
            _stream_agent_run(
                agent=agent,
                resolved=resolved,
                task=body.task.strip(),
                context=body.context,
                run_id=run_id,
                agent_id=str(agent.id),
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming path
    result = await _execute_agent_llm(
        agent=agent,
        resolved=resolved,
        task=body.task.strip(),
        context=body.context,
        run_id=run_id,
    )

    return AgentRunResponse(
        run_id=result["run_id"],
        agent_id=str(agent.id),
        status=result["status"],
        output=result["output"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        duration_ms=result["duration_ms"],
    )
