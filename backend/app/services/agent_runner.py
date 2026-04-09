"""Agent runner with memory context injection.

Provides AgentRunner for executing agent tasks with optional memory
persistence. Memory-enabled agents store run outputs and inject prior
context into subsequent runs.
"""

import uuid
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.agent import Agent
from app.models.agent_memory import AgentMemory

logger = logging.getLogger(__name__)

# Default number of prior run outputs to inject as memory context
DEFAULT_MEMORY_LIMIT = 5

# Maximum characters to store per memory entry (truncated if longer)
MAX_MEMORY_OUTPUT_LENGTH = 2000


class AgentRunner:
    """Executes agent tasks with optional memory context.

    When an agent has `memory_enabled=True`, the runner:
    1. Loads recent memory entries before building the prompt
    2. Injects prior run context into the system prompt
    3. Saves the run output to memory after completion
    """

    def __init__(self, db: Optional[AsyncSession] = None):
        self._db = db

    # ─── Memory methods ──────────────────────────────────────────────────

    async def load_memory(
        self, agent_id: str, limit: int = DEFAULT_MEMORY_LIMIT
    ) -> list[dict]:
        """Load recent memory entries for an agent.

        Args:
            agent_id: The agent whose memory to load.
            limit: Maximum number of entries to return (most recent first,
                   then reversed to chronological order).

        Returns:
            List of dicts with task, output, and created_at fields,
            ordered oldest-to-newest for natural prompt injection.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AgentMemory)
                .where(AgentMemory.agent_id == agent_id)
                .order_by(AgentMemory.created_at.desc())
                .limit(limit)
            )
            entries = result.scalars().all()

        # Reverse to chronological order for prompt context
        return [
            {
                "task": e.task,
                "output": e.output_summary,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in reversed(entries)
        ]

    async def save_memory(
        self, agent_id: str, run_id: str, task: str, output: str
    ) -> AgentMemory:
        """Save a run output to agent memory.

        Args:
            agent_id: The agent this memory belongs to.
            run_id: The run that produced this output.
            task: The task/prompt that was given.
            output: The agent's output (truncated to MAX_MEMORY_OUTPUT_LENGTH).

        Returns:
            The created AgentMemory record.
        """
        summary = output[:MAX_MEMORY_OUTPUT_LENGTH] if len(output) > MAX_MEMORY_OUTPUT_LENGTH else output

        async with AsyncSessionLocal() as session:
            entry = AgentMemory(
                agent_id=agent_id,
                run_id=run_id,
                task=task,
                output_summary=summary,
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry

    def format_memory_context(self, memories: list[dict]) -> str:
        """Format memory entries into a string for system prompt injection.

        Args:
            memories: List of memory dicts from load_memory().

        Returns:
            Formatted string suitable for appending to a system prompt.
        """
        if not memories:
            return ""

        lines = ["## Prior Run Context", ""]
        for i, mem in enumerate(memories, 1):
            lines.append(f"### Run {i} ({mem.get('created_at', 'unknown')})")
            lines.append(f"**Task:** {mem['task']}")
            lines.append(f"**Output:** {mem['output']}")
            lines.append("")

        return "\n".join(lines)

    async def build_system_prompt(
        self, agent: Agent, memory_limit: int = DEFAULT_MEMORY_LIMIT
    ) -> str:
        """Build the full system prompt, optionally injecting memory context.

        Args:
            agent: The Agent ORM object.
            memory_limit: Number of prior runs to include.

        Returns:
            The complete system prompt string.
        """
        base_prompt = agent.system_prompt or ""

        if not agent.memory_enabled:
            return base_prompt

        agent_id = str(agent.id)
        memories = await self.load_memory(agent_id, limit=memory_limit)

        if not memories:
            return base_prompt

        memory_context = self.format_memory_context(memories)
        return f"{base_prompt}\n\n{memory_context}"

    async def run(
        self,
        agent: Agent,
        task: str,
        memory_limit: int = DEFAULT_MEMORY_LIMIT,
    ) -> dict:
        """Execute an agent task with memory support.

        This is the main entry point. It:
        1. Builds the system prompt (with memory if enabled)
        2. Executes the task (placeholder -- full implementation in E1.2)
        3. Saves the output to memory if the agent has memory_enabled

        Args:
            agent: The Agent ORM object to run.
            task: The task/prompt to execute.
            memory_limit: Number of prior memory entries to inject.

        Returns:
            Dict with run_id, output, and metadata.
        """
        run_id = str(uuid.uuid4())
        agent_id = str(agent.id)

        # Build prompt with memory context
        system_prompt = await self.build_system_prompt(agent, memory_limit)

        logger.info(
            f"Running agent {agent.name} (id={agent_id}, run={run_id}, "
            f"memory={'on' if agent.memory_enabled else 'off'})"
        )

        # --- Task execution placeholder ---
        # Full LLM call + tool loop will be added in E1.2.
        # For now, return the built prompt metadata so callers can verify
        # memory injection is working.
        output = f"[AgentRunner] Task received: {task}"

        # Save to memory if enabled
        if agent.memory_enabled:
            await self.save_memory(agent_id, run_id, task, output)
            logger.info(f"Saved memory entry for agent {agent_id}, run {run_id}")

        return {
            "run_id": run_id,
            "agent_id": agent_id,
            "agent_name": agent.name,
            "task": task,
            "output": output,
            "system_prompt_used": system_prompt,
            "memory_enabled": agent.memory_enabled,
            "memory_entries_injected": memory_limit if agent.memory_enabled else 0,
        }
