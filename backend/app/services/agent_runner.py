"""Agent runner with iterative tool execution loop and memory context.

Runs an agent through multiple iterations:
  1. Send task + context to LLM
  2. Parse LLM output for tool commands (CMD: blocks)
  3. Execute detected tools via command_executor
  4. Feed tool results back as context for next iteration
  5. Repeat until done, max_iterations, or timeout

Memory-enabled agents persist run outputs and inject prior context
into subsequent runs via AgentMemory.

Uses the existing ModelClient, command_classifier, and command_executor
infrastructure rather than introducing new abstractions.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Model, Provider
from app.models.agent_memory import AgentMemory
from app.models.agent_run import AgentRun

logger = logging.getLogger(__name__)

# Default number of prior run outputs to inject as memory context
DEFAULT_MEMORY_LIMIT = 5

# Maximum characters to store per memory entry (truncated if longer)
MAX_MEMORY_OUTPUT_LENGTH = 2000


class AgentRunner:
    """Iterative agent execution with tool use and optional memory."""

    def __init__(
        self,
        agent,
        model: Model,
        provider: Provider,
        *,
        project_path: Optional[Path] = None,
    ):
        """
        Args:
            agent: Agent ORM object with system_prompt, tools, max_iterations,
                   timeout_seconds attributes.
            model: Model ORM object (resolved).
            provider: Provider ORM object (resolved).
            project_path: Working directory for shell commands (optional).
        """
        self.agent = agent
        self.model = model
        self.provider = provider
        self.project_path = project_path or Path.cwd()
        self.max_iterations = getattr(agent, "max_iterations", 10) or 10
        self.timeout = getattr(agent, "timeout_seconds", 300) or 300
        self.iterations: list[dict] = []

    # ------------------------------------------------------------------
    # Memory methods
    # ------------------------------------------------------------------

    async def load_memory(
        self, agent_id: str, limit: int = DEFAULT_MEMORY_LIMIT
    ) -> list[dict]:
        """Load recent memory entries for an agent.

        Returns list of dicts ordered oldest-to-newest for prompt injection.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AgentMemory)
                .where(AgentMemory.agent_id == agent_id)
                .order_by(AgentMemory.created_at.desc())
                .limit(limit)
            )
            entries = result.scalars().all()

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
        """Save a run output to agent memory (truncated to MAX_MEMORY_OUTPUT_LENGTH)."""
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

    @staticmethod
    def format_memory_context(memories: list[dict]) -> str:
        """Format memory entries for system prompt injection."""
        if not memories:
            return ""

        lines = ["## Prior Run Context", ""]
        for i, mem in enumerate(memories, 1):
            lines.append(f"### Run {i} ({mem.get('created_at', 'unknown')})")
            lines.append(f"**Task:** {mem['task']}")
            lines.append(f"**Output:** {mem['output']}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Build system prompt with tool-use instructions appended.

        For models that support native function calling the tool schemas are
        passed via LiteLLM's ``tools=`` parameter, so we only append a brief
        note.  For text-based fallback models we embed the full CMD: fragment
        so the model knows what syntax to use.
        """
        from app.services.tool_registry import (
            get_tool_prompt_fragment,
            provider_supports_function_calling,
            resolve_agent_tools,
        )

        base = getattr(self.agent, "system_prompt", "") or ""
        tool_names = resolve_agent_tools(getattr(self.agent, "tools", None))

        if not tool_names:
            return base

        uses_native = provider_supports_function_calling(
            self.provider.name, self.model.model_id or ""
        )

        if uses_native:
            # The tool schemas are sent separately; just remind the model.
            suffix = (
                "\n\nYou have access to tools (read_file, write_file, list_dir, "
                "run_shell, install_package, web_fetch). Use them to complete the "
                "task. When finished, provide your final answer."
            )
        else:
            suffix = "\n\n" + get_tool_prompt_fragment(tool_names)

        return base + suffix

    async def _call_llm(self, messages: list) -> tuple[str, list, int, int]:
        """Make one LLM call, returning (response_text, tool_calls, input_tokens, output_tokens).

        When the provider supports native function calling (OpenAI tool_calls format),
        uses ``call_model_with_tools`` so the model receives structured schemas and
        returns structured JSON arguments.  Falls back to plain text streaming with
        CMD: parsing for models that do not support function calling.

        ``tool_calls`` is a list of dicts: [{"id", "name", "arguments"}, ...]
        An empty list means the model responded with plain text only.
        """
        from app.services.model_client import ModelClient
        from app.services.tool_registry import (
            get_tool_schemas,
            provider_supports_function_calling,
            resolve_agent_tools,
        )

        client = ModelClient()
        tool_names = resolve_agent_tools(getattr(self.agent, "tools", None))
        uses_native = bool(tool_names) and provider_supports_function_calling(
            self.provider.name, self.model.model_id or ""
        )

        if uses_native:
            schemas = get_tool_schemas(tool_names)
            response_text, tool_calls, input_tokens, output_tokens = (
                await client.call_model_with_tools(
                    model=self.model,
                    provider=self.provider,
                    messages=messages,
                    tools=schemas,
                    temperature=0.2,
                    max_tokens=8000,
                )
            )
            return response_text, tool_calls, input_tokens, output_tokens

        # ── Text-streaming fallback (CMD: blocks) ────────────────────────────
        stream = await client.call_model(
            model=self.model,
            provider=self.provider,
            messages=messages,
            stream=True,
            temperature=0.2,
            max_tokens=8000,
        )

        chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0

        async for chunk in stream:
            delta = ""
            try:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta.content or ""
                elif isinstance(chunk, dict):
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
            except Exception:
                pass

            if delta:
                chunks.append(delta)

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

        return "".join(chunks), [], input_tokens, output_tokens

    async def _execute_commands(self, commands: list[str]) -> list[dict]:
        """Execute parsed CMD: commands and return results."""
        from app.services.command_executor import run_command
        from app.services.command_classifier import classify_command, CommandTier

        results: list[dict] = []
        for cmd in commands:
            tier = classify_command(cmd)

            # Skip blocked commands
            if tier == CommandTier.BLOCKED:
                results.append({
                    "command": cmd,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Command blocked by sandbox policy.",
                    "success": False,
                    "tier": tier.value,
                })
                continue

            try:
                exit_code, stdout, stderr, duration_ms = await run_command(
                    cmd, self.project_path, timeout_sec=60,
                )
                results.append({
                    "command": cmd,
                    "exit_code": exit_code,
                    "stdout": stdout[:2000] if stdout else "",
                    "stderr": stderr[:2000] if stderr else "",
                    "success": exit_code == 0,
                    "tier": tier.value,
                    "duration_ms": duration_ms,
                })
            except Exception as e:
                logger.error("Command execution failed: %s — %s", cmd, e)
                results.append({
                    "command": cmd,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": str(e),
                    "success": False,
                    "tier": tier.value,
                })

        return results

    async def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """Execute native function-call tool_calls and return structured results.

        Each item in ``tool_calls`` is {"id", "name", "arguments"}.
        Returns a parallel list of result dicts with "success", "output", "name", "id".
        """
        from app.services.command_executor import execute_tool_call

        results: list[dict] = []
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("arguments", {})
            try:
                result = await execute_tool_call(name, args, self.project_path)
            except Exception as exc:
                logger.error("Tool call '%s' raised: %s", name, exc)
                result = {"success": False, "output": str(exc)}

            results.append(
                {
                    "id": tc.get("id", ""),
                    "name": name,
                    "arguments": args,
                    "success": result.get("success", False),
                    "output": result.get("output", ""),
                }
            )
        return results

    @staticmethod
    def _format_native_tool_results(results: list[dict]) -> str:
        """Format native tool call results for injection into the next LLM turn."""
        parts: list[str] = []
        for r in results:
            status = "OK" if r["success"] else "ERROR"
            output = (r.get("output") or "").strip()
            if len(output) > 4000:
                output = output[:4000] + "\n…(truncated)"
            parts.append(
                f"[tool: {r['name']} | {status}]\n{output}"
            )
        return "\n\n".join(parts)

    @staticmethod
    def _format_tool_results(results: list[dict]) -> str:
        """Format CMD: tool results as context for the next LLM turn."""
        parts: list[str] = []
        for r in results:
            lines = [f"$ {r['command']}", f"[exit={r['exit_code']}]"]
            if r["stdout"]:
                lines.append(f"STDOUT:\n{r['stdout']}")
            if r["stderr"]:
                lines.append(f"STDERR:\n{r['stderr']}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    @staticmethod
    def _check_done(response_text: str) -> Optional[str]:
        """If the response contains a DONE: signal, return the final answer."""
        if "DONE:" in response_text:
            idx = response_text.index("DONE:")
            return response_text[idx + 5:].strip()
        return None

    # ------------------------------------------------------------------
    # Public API — non-streaming
    # ------------------------------------------------------------------

    async def run(
        self,
        task: str,
        context: Optional[dict] = None,
        *,
        agentic_emit=None,
        session_id: Optional[str] = None,
    ) -> dict:
        """Execute agent with iterative tool loop. Returns final result dict.

        Parameters
        ----------
        task:
            The user task string.
        context:
            Optional extra context dict.
        agentic_emit:
            Optional async ``(event_dict) -> None`` callback wired to the
            workbench SSE push helper.  When provided the run passes through
            the full AgenticOrchestrator state machine so every state
            transition is emitted as a telemetry event.
        session_id:
            Workbench session owning this run (used for goal extraction context).
        """
        from app.services.command_executor import parse_cmd_blocks

        # ── Agentic orchestration wrapper ─────────────────────────────
        # When an emit callback is provided the run is driven through the
        # goal → plan → execute → verify state machine so telemetry reflects
        # true agentic behaviour rather than raw iteration events only.
        if agentic_emit is not None:
            from app.services.agentic_orchestrator import AgenticOrchestrator

            orchestrator = AgenticOrchestrator(
                session_id=session_id or "standalone",
                emit=agentic_emit,
            )

            async def _execute_fn(prompt, goal, plan):
                # Run the actual iteration loop without re-entering orchestration
                return await self.run(prompt, context)

            orch_result = await orchestrator.run(task, _execute_fn)
            # Merge orchestrator metadata into the underlying run result
            inner_result = orch_result.get("result", {})
            inner_result.update(
                {
                    "agentic_run_id": orch_result["run_id"],
                    "agentic_goal_id": orch_result["goal_id"],
                    "agentic_plan_id": orch_result["plan_id"],
                    "agentic_state_history": orch_result["state_history"],
                    "agentic_verification": orch_result["verification"],
                }
            )
            return inner_result

        run_id = str(uuid.uuid4())
        start_time = time.time()

        # Build initial messages (with memory context if enabled)
        system_prompt = self._build_system_prompt()
        if getattr(self.agent, "memory_enabled", False):
            agent_id = str(self.agent.id)
            memories = await self.load_memory(agent_id)
            memory_ctx = self.format_memory_context(memories)
            if memory_ctx:
                system_prompt = f"{system_prompt}\n\n{memory_ctx}"

        messages = [{"role": "system", "content": system_prompt}]

        user_content = task
        if context:
            user_content += f"\n\nAdditional context:\n{json.dumps(context, indent=2)}"
        messages.append({"role": "user", "content": user_content})

        final_output = ""
        total_input_tokens = 0
        total_output_tokens = 0

        for iteration in range(self.max_iterations):
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                logger.warning(
                    "Agent run %s timed out after %.1fs", run_id, elapsed
                )
                self.iterations.append({
                    "iteration": iteration,
                    "type": "timeout",
                })
                break

            # Call LLM
            try:
                response_text, native_tool_calls, in_tok, out_tok = await self._call_llm(messages)
                total_input_tokens += in_tok
                total_output_tokens += out_tok
            except Exception as e:
                logger.error("LLM call failed in iteration %d: %s", iteration, e)
                final_output = f"Error in iteration {iteration}: {e}"
                self.iterations.append({
                    "iteration": iteration,
                    "type": "error",
                    "error": str(e),
                })
                break

            # ── Native function-call path ─────────────────────────────
            if native_tool_calls:
                tool_results = await self._execute_tool_calls(native_tool_calls)
                self.iterations.append({
                    "iteration": iteration,
                    "type": "tool_use",
                    "response_preview": response_text[:500],
                    "tool_calls": [
                        {"name": r["name"], "success": r["success"]}
                        for r in tool_results
                    ],
                })

                # Feed results back using OpenAI tool_calls multi-turn format
                assistant_msg: dict = {"role": "assistant", "content": response_text or None}
                assistant_msg["tool_calls"] = [
                    {
                        "id": r["id"],
                        "type": "function",
                        "function": {
                            "name": r["name"],
                            "arguments": json.dumps(r["arguments"]),
                        },
                    }
                    for r in tool_results
                ]
                messages.append(assistant_msg)
                for r in tool_results:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": r["id"],
                            "content": r["output"],
                        }
                    )
                continue

            # ── Text-parsing fallback path (CMD: blocks) ──────────────

            # Check for DONE signal
            done_answer = self._check_done(response_text)
            if done_answer is not None:
                final_output = done_answer
                self.iterations.append({
                    "iteration": iteration,
                    "type": "done",
                    "output": done_answer,
                })
                break

            # Parse for CMD: blocks
            commands = parse_cmd_blocks(response_text)

            if not commands:
                # No tools and no DONE — treat response as final output
                final_output = response_text
                self.iterations.append({
                    "iteration": iteration,
                    "type": "final",
                    "output": response_text[:500],
                })
                break

            # Execute commands
            tool_results = await self._execute_commands(commands)

            self.iterations.append({
                "iteration": iteration,
                "type": "tool_use",
                "response_preview": response_text[:500],
                "commands": [r["command"] for r in tool_results],
                "results_summary": [
                    {"cmd": r["command"], "success": r["success"], "exit": r["exit_code"]}
                    for r in tool_results
                ],
            })

            # Feed results back for next iteration
            messages.append({"role": "assistant", "content": response_text})
            feedback = self._format_tool_results(tool_results)
            messages.append({
                "role": "user",
                "content": (
                    f"Tool execution results:\n{feedback}\n\n"
                    "Continue with the task. When done, respond with "
                    "DONE: followed by your final answer."
                ),
            })
        else:
            # max_iterations reached without DONE or final output
            if not final_output:
                final_output = "Max iterations reached without completion."

        duration_ms = int((time.time() - start_time) * 1000)

        # Save to memory if enabled
        if getattr(self.agent, "memory_enabled", False) and final_output:
            try:
                await self.save_memory(str(self.agent.id), run_id, task, final_output)
            except Exception as e:
                logger.warning("Failed to save agent memory: %s", e)

        status = "completed" if final_output and "Error" not in final_output else "failed"

        # Persist AgentRun record
        try:
            agent_id = str(self.agent.id)
            async with AsyncSessionLocal() as session:
                agent_run = AgentRun(
                    id=uuid.UUID(run_id),
                    agent_id=uuid.UUID(agent_id),
                    task=task,
                    status=status,
                    output=final_output,
                    tool_log=self.iterations,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    duration_ms=duration_ms,
                )
                session.add(agent_run)
                await session.commit()
        except Exception as e:
            logger.warning("Failed to persist AgentRun: %s", e)

        return {
            "run_id": run_id,
            "status": status,
            "output": final_output,
            "iterations": self.iterations,
            "iteration_count": len(self.iterations),
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "duration_ms": duration_ms,
        }

    # ------------------------------------------------------------------
    # Public API — streaming (SSE events per iteration)
    # ------------------------------------------------------------------

    async def run_stream(
        self, task: str, context: Optional[dict] = None
    ) -> AsyncGenerator[dict, None]:
        """Execute agent with streaming events per iteration.

        Yields dicts with an "event" key that callers can serialise as SSE.
        Event types: run_started, iteration_started, chunk, tool_call,
        tool_result, iteration_complete, done, timeout, max_iterations, error.
        """
        from app.services.command_executor import parse_cmd_blocks
        from app.services.model_client import ModelClient

        run_id = str(uuid.uuid4())
        start_time = time.time()

        messages = [{"role": "system", "content": self._build_system_prompt()}]

        user_content = task
        if context:
            user_content += f"\n\nAdditional context:\n{json.dumps(context, indent=2)}"
        messages.append({"role": "user", "content": user_content})

        total_input_tokens = 0
        total_output_tokens = 0

        client = ModelClient()
        yield {"event": "run_started", "run_id": run_id}

        for iteration in range(self.max_iterations):
            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                yield {
                    "event": "timeout",
                    "iteration": iteration,
                    "elapsed_ms": int(elapsed * 1000),
                }
                return

            yield {"event": "iteration_started", "iteration": iteration}

            # ── Branch: native function calling vs text streaming ─────
            from app.services.tool_registry import (
                get_tool_schemas,
                provider_supports_function_calling,
                resolve_agent_tools,
            )

            tool_names = resolve_agent_tools(getattr(self.agent, "tools", None))
            uses_native = bool(tool_names) and provider_supports_function_calling(
                self.provider.name, self.model.model_id or ""
            )

            if uses_native:
                # Native tool-calling: non-streaming, structured responses
                schemas = get_tool_schemas(tool_names)
                try:
                    response_text, native_tool_calls, in_tok, out_tok = (
                        await client.call_model_with_tools(
                            model=self.model,
                            provider=self.provider,
                            messages=messages,
                            tools=schemas,
                            temperature=0.2,
                            max_tokens=8000,
                        )
                    )
                    total_input_tokens += in_tok
                    total_output_tokens += out_tok
                except Exception as e:
                    yield {"event": "error", "iteration": iteration, "message": str(e)}
                    return

                if response_text:
                    yield {"event": "chunk", "data": response_text}

                if native_tool_calls:
                    for tc in native_tool_calls:
                        yield {
                            "event": "tool_call",
                            "iteration": iteration,
                            "command": f"{tc['name']}({json.dumps(tc['arguments'])})",
                        }

                    tc_results = await self._execute_tool_calls(native_tool_calls)

                    for r in tc_results:
                        yield {
                            "event": "tool_result",
                            "iteration": iteration,
                            "command": r["name"],
                            "success": r["success"],
                            "stdout": r["output"][:500],
                            "stderr": "",
                            "exit_code": 0 if r["success"] else -1,
                        }

                    yield {"event": "iteration_complete", "iteration": iteration}

                    # Feed results back in OpenAI multi-turn format
                    assistant_msg: dict = {
                        "role": "assistant",
                        "content": response_text or None,
                        "tool_calls": [
                            {
                                "id": r["id"],
                                "type": "function",
                                "function": {
                                    "name": r["name"],
                                    "arguments": json.dumps(r["arguments"]),
                                },
                            }
                            for r in tc_results
                        ],
                    }
                    messages.append(assistant_msg)
                    for r in tc_results:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": r["id"],
                                "content": r["output"],
                            }
                        )
                    continue

                # No tool calls — final answer
                yield {
                    "event": "done",
                    "output": response_text,
                    "run_id": run_id,
                    "iteration_count": iteration + 1,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "duration_ms": int((time.time() - start_time) * 1000),
                }
                return

            # ── Text-streaming path (CMD: blocks) ────────────────────
            chunks: list[str] = []
            try:
                stream = await client.call_model(
                    model=self.model,
                    provider=self.provider,
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
                        elif isinstance(chunk, dict):
                            delta = (
                                chunk.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                    except Exception:
                        pass

                    if delta:
                        chunks.append(delta)
                        yield {"event": "chunk", "data": delta}

                    # Capture usage
                    try:
                        usage = None
                        if hasattr(chunk, "usage") and chunk.usage:
                            usage = chunk.usage
                        elif isinstance(chunk, dict) and chunk.get("usage"):
                            usage = chunk["usage"]
                        if usage:
                            total_input_tokens = (
                                getattr(usage, "prompt_tokens", 0)
                                or (usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0)
                            )
                            total_output_tokens = (
                                getattr(usage, "completion_tokens", 0)
                                or (usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0)
                            )
                    except Exception:
                        pass

            except Exception as e:
                yield {"event": "error", "iteration": iteration, "message": str(e)}
                return

            response_text = "".join(chunks)

            # Check for DONE signal
            done_answer = self._check_done(response_text)
            if done_answer is not None:
                yield {
                    "event": "done",
                    "output": done_answer,
                    "run_id": run_id,
                    "iteration_count": iteration + 1,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "duration_ms": int((time.time() - start_time) * 1000),
                }
                return

            # Parse for CMD: blocks
            commands = parse_cmd_blocks(response_text)

            if not commands:
                # No tools, no DONE — treat as final output
                yield {
                    "event": "done",
                    "output": response_text,
                    "run_id": run_id,
                    "iteration_count": iteration + 1,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "duration_ms": int((time.time() - start_time) * 1000),
                }
                return

            # Execute commands with per-tool events
            from app.services.command_executor import run_command
            from app.services.command_classifier import classify_command, CommandTier

            tool_results: list[dict] = []
            for cmd in commands:
                yield {"event": "tool_call", "iteration": iteration, "command": cmd}

                tier = classify_command(cmd)
                if tier == CommandTier.BLOCKED:
                    result = {
                        "command": cmd,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": "Command blocked by sandbox policy.",
                        "success": False,
                    }
                else:
                    try:
                        exit_code, stdout, stderr, duration_ms = await run_command(
                            cmd, self.project_path, timeout_sec=60,
                        )
                        result = {
                            "command": cmd,
                            "exit_code": exit_code,
                            "stdout": stdout[:2000] if stdout else "",
                            "stderr": stderr[:2000] if stderr else "",
                            "success": exit_code == 0,
                        }
                    except Exception as e:
                        result = {
                            "command": cmd,
                            "exit_code": -1,
                            "stdout": "",
                            "stderr": str(e),
                            "success": False,
                        }

                tool_results.append(result)
                yield {
                    "event": "tool_result",
                    "iteration": iteration,
                    "command": cmd,
                    "exit_code": result["exit_code"],
                    "stdout": result["stdout"][:500],
                    "stderr": result["stderr"][:500],
                    "success": result["success"],
                }

            yield {"event": "iteration_complete", "iteration": iteration}

            # Feed results back for next iteration
            messages.append({"role": "assistant", "content": response_text})
            feedback = self._format_tool_results(tool_results)
            messages.append({
                "role": "user",
                "content": (
                    f"Tool execution results:\n{feedback}\n\n"
                    "Continue with the task. When done, say DONE: "
                    "followed by your final answer."
                ),
            })

        # max_iterations exhausted
        yield {
            "event": "max_iterations",
            "iterations": self.max_iterations,
            "duration_ms": int((time.time() - start_time) * 1000),
        }
