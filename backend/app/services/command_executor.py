"""Execute shell commands emitted by workbench agents (CMD: blocks).

Respects the 3-tier classifier + per-session bypass mode. Captures stdout,
stderr, exit code, duration. Persists everything to the workbench_commands
audit table.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from app.database import AsyncSessionLocal
from app.services.command_classifier import (
    classify_command, CommandTier, load_project_trusted_patterns
)

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 100 * 1024  # 100KB per command
DEFAULT_TIMEOUT_SEC = 300


# ─── CMD: block parser ────────────────────────────────────────────────────────
_CMD_BLOCK_RE = re.compile(
    r"^\s*CMD:\s*(?P<cmd>.+?)\s*$",
    re.MULTILINE
)


def parse_cmd_blocks(response_text: str) -> list[str]:
    """Extract CMD: commands from an agent's response.

    Supported format:
        CMD: npm install
        CMD: pytest tests/ -v
        CMD: git add .

    Returns a list of command strings, in the order they appeared.
    Empty commands and lines that are CMD: alone with no command are skipped.
    """
    commands = []
    for m in _CMD_BLOCK_RE.finditer(response_text or ""):
        cmd = m.group("cmd").strip()
        # Strip wrapping backticks if present
        if cmd.startswith("`") and cmd.endswith("`"):
            cmd = cmd[1:-1].strip()
        if cmd:
            commands.append(cmd)
    return commands


def strip_cmd_blocks_from_response(response_text: str) -> str:
    """Remove CMD: lines from a response so they don't appear in agent_reply commentary."""
    return _CMD_BLOCK_RE.sub("", response_text or "").strip()


# ─── Command execution record helpers ─────────────────────────────────────────
async def create_command_record(
    session_id: str,
    command: str,
    tier: CommandTier,
    *,
    pipeline_id: Optional[str] = None,
    phase_run_id: Optional[str] = None,
    turn_number: Optional[int] = None,
    initial_status: str = "pending",
) -> str:
    """Insert a new workbench_commands row and return its id."""
    from app.models.command_execution import CommandExecution
    import uuid as _uuid
    rec_id = str(_uuid.uuid4())
    async with AsyncSessionLocal() as db:
        rec = CommandExecution(
            id=rec_id,
            session_id=session_id,
            pipeline_id=pipeline_id,
            phase_run_id=phase_run_id,
            turn_number=turn_number,
            command=command,
            tier=tier.value,
            status=initial_status,
        )
        db.add(rec)
        await db.commit()
    return rec_id


async def update_command_record(record_id: str, **fields):
    """Update fields on a workbench_commands row."""
    from app.models.command_execution import CommandExecution
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        rec = (await db.execute(select(CommandExecution).where(CommandExecution.id == record_id))).scalar_one_or_none()
        if rec:
            for k, v in fields.items():
                setattr(rec, k, v)
            await db.commit()


# ─── Command runner ───────────────────────────────────────────────────────────
async def run_command(
    command: str,
    cwd: Path,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> Tuple[int, str, str, int]:
    """Run one shell command. Returns (exit_code, stdout, stderr, duration_ms).

    Outputs are truncated to MAX_OUTPUT_BYTES with a "…truncated" tail.
    On timeout, returns (-1, partial_stdout, "Timed out after Xs", duration).
    """
    started = datetime.utcnow()
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env={**os.environ},
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            exit_code = proc.returncode if proc.returncode is not None else -1
        except asyncio.TimeoutError:
            proc.kill()
            try:
                stdout_b, stderr_b = await proc.communicate()
            except Exception:
                stdout_b, stderr_b = b"", b""
            exit_code = -1
            stderr_b = (stderr_b or b"") + f"\n\n[command killed after {timeout_sec}s timeout]".encode()
    except Exception as e:
        duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
        return -1, "", f"Failed to spawn command: {e}", duration_ms

    duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    stdout = (stdout_b or b"").decode("utf-8", errors="replace")
    stderr = (stderr_b or b"").decode("utf-8", errors="replace")
    if len(stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
        stdout = stdout[:MAX_OUTPUT_BYTES // 2] + "\n\n…output truncated…\n"
    if len(stderr.encode("utf-8")) > MAX_OUTPUT_BYTES:
        stderr = stderr[:MAX_OUTPUT_BYTES // 2] + "\n\n…output truncated…\n"
    return exit_code, stdout, stderr, duration_ms


async def execute_and_record(
    record_id: str,
    command: str,
    cwd: Path,
    *,
    bypass_used: bool = False,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict:
    """Run a command and persist stdout/stderr/exit_code to its record.

    Returns a dict with the execution result for inclusion in SSE events.
    """
    await update_command_record(
        record_id,
        status="running",
        started_at=datetime.utcnow(),
        bypass_used=bypass_used,
    )
    exit_code, stdout, stderr, duration_ms = await run_command(command, cwd, timeout_sec=timeout_sec)
    status = "completed" if exit_code == 0 else "failed"
    await update_command_record(
        record_id,
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        completed_at=datetime.utcnow(),
    )
    return {
        "command_id": record_id,
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms,
        "status": status,
        "bypass_used": bypass_used,
    }


def classify_with_project_trust(command: str, sandbox_mode: str, project_path: Optional[str]) -> CommandTier:
    """Convenience: classify honoring project-level trusted patterns."""
    trusted = load_project_trusted_patterns(project_path) if project_path else []
    return classify_command(command, sandbox_mode=sandbox_mode, extra_trusted_patterns=trusted)


def format_command_for_context(result: dict) -> str:
    """Render a command result as a compact string the LLM can consume on the next turn."""
    cmd = result.get("command", "")
    exit_code = result.get("exit_code", 0)
    stdout = (result.get("stdout") or "").strip()
    stderr = (result.get("stderr") or "").strip()
    # Cap per-stream to 2KB to keep context budget reasonable
    if len(stdout) > 2000:
        stdout = stdout[:2000] + "\n…(truncated)"
    if len(stderr) > 2000:
        stderr = stderr[:2000] + "\n…(truncated)"
    parts = [f"$ {cmd}", f"[exit={exit_code}]"]
    if stdout:
        parts.append(f"STDOUT:\n{stdout}")
    if stderr:
        parts.append(f"STDERR:\n{stderr}")
    return "\n".join(parts)
