"""Agent CRUD endpoints for DevForgeAI."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.agent import Agent, DEFAULT_AGENTS
from app.middleware.auth import verify_api_key
from pydantic import BaseModel
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/agents", tags=["agents"], dependencies=[Depends(verify_api_key)])


class AgentCreate(BaseModel):
    name: str
    agent_type: str
    description: Optional[str] = None
    system_prompt: str
    model_id: Optional[str] = None
    tools: List[str] = []
    memory_enabled: bool = True
    max_iterations: int = 10
    timeout_seconds: int = 300


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model_id: Optional[str] = None
    tools: Optional[List[str]] = None
    memory_enabled: Optional[bool] = None
    max_iterations: Optional[int] = None
    timeout_seconds: Optional[int] = None
    is_active: Optional[bool] = None


class AgentResponse(BaseModel):
    id: str
    name: str
    agent_type: str
    description: Optional[str]
    system_prompt: str
    model_id: Optional[str]
    tools: List[str]
    memory_enabled: bool
    max_iterations: int
    timeout_seconds: int
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class AgentListResponse(BaseModel):
    data: List[AgentResponse]
    total: int


@router.get("", response_model=AgentListResponse)
async def list_agents(
    agent_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """List all agents, optionally filtered by type."""
    query = select(Agent)
    
    if agent_type:
        query = query.where(Agent.agent_type == agent_type)
    
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    agents = result.scalars().all()
    
    # If no agents in database, return defaults
    if not agents:
        default_agents = []
        for agent_data in DEFAULT_AGENTS:
            default_agents.append(AgentResponse(
                id=f"default-{agent_data['agent_type']}",
                name=agent_data["name"],
                agent_type=agent_data["agent_type"],
                description=agent_data.get("description"),
                system_prompt=agent_data["system_prompt"],
                model_id=None,
                tools=agent_data.get("tools", []),
                memory_enabled=agent_data.get("memory_enabled", True),
                max_iterations=agent_data.get("max_iterations", 10),
                timeout_seconds=agent_data.get("timeout_seconds", 300),
                is_active=True,
                created_at="default",
                updated_at="default"
            ))
        return AgentListResponse(data=default_agents, total=len(default_agents))
    
    # Get total count
    count_query = select(Agent)
    if agent_type:
        count_query = count_query.where(Agent.agent_type == agent_type)
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return AgentListResponse(
        data=[AgentResponse.model_validate(a) for a in agents],
        total=total
    )


@router.post("", response_model=AgentResponse)
async def create_agent(
    agent: AgentCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new agent."""
    # Get default user
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
        tools=agent.tools,
        memory_enabled=agent.memory_enabled,
        max_iterations=agent.max_iterations,
        timeout_seconds=agent.timeout_seconds,
        user_id=user.id if user else None
    )
    
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)
    
    return AgentResponse.model_validate(new_agent)


@router.get("/defaults", response_model=AgentListResponse)
async def get_default_agents():
    """Get the default agent configurations."""
    agents = []
    for agent_data in DEFAULT_AGENTS:
        agents.append(AgentResponse(
            id=str(uuid.uuid4()),  # Placeholder ID
            name=agent_data["name"],
            agent_type=agent_data["agent_type"],
            description=agent_data.get("description"),
            system_prompt=agent_data["system_prompt"],
            model_id=None,
            tools=agent_data.get("tools", []),
            memory_enabled=agent_data.get("memory_enabled", True),
            max_iterations=agent_data.get("max_iterations", 10),
            timeout_seconds=agent_data.get("timeout_seconds", 300),
            is_active=True,
            created_at="",
            updated_at=""
        ))
    
    return AgentListResponse(data=agents, total=len(agents))


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific agent by ID."""
    try:
        agent_uuid = uuid.UUID(agent_id)
        result = await db.execute(select(Agent).where(Agent.id == agent_uuid))
    except ValueError:
        result = await db.execute(select(Agent).where(Agent.name == agent_id))
    
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return AgentResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    updates: AgentUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update an agent."""
    try:
        agent_uuid = uuid.UUID(agent_id)
        result = await db.execute(select(Agent).where(Agent.id == agent_uuid))
    except ValueError:
        result = await db.execute(select(Agent).where(Agent.name == agent_id))
    
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if updates.name is not None:
        agent.name = updates.name
    if updates.description is not None:
        agent.description = updates.description
    if updates.system_prompt is not None:
        agent.system_prompt = updates.system_prompt
    if updates.model_id is not None:
        agent.model_id = uuid.UUID(updates.model_id)
    if updates.tools is not None:
        agent.tools = updates.tools
    if updates.memory_enabled is not None:
        agent.memory_enabled = updates.memory_enabled
    if updates.max_iterations is not None:
        agent.max_iterations = updates.max_iterations
    if updates.timeout_seconds is not None:
        agent.timeout_seconds = updates.timeout_seconds
    if updates.is_active is not None:
        agent.is_active = updates.is_active
    
    await db.commit()
    await db.refresh(agent)
    return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete an agent."""
    try:
        agent_uuid = uuid.UUID(agent_id)
        result = await db.execute(select(Agent).where(Agent.id == agent_uuid))
    except ValueError:
        result = await db.execute(select(Agent).where(Agent.name == agent_id))
    
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    await db.delete(agent)
    await db.commit()
    return {"status": "deleted"}