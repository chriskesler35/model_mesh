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
from typing import Optional, Tuple, Dict

from app.database import AsyncSessionLocal
from app.services.command_classifier import (
    classify_command, CommandTier, load_project_trusted_patterns
)

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 100 * 1024  # 100KB per command
DEFAULT_TIMEOUT_SEC = 300


def _is_git_command(command: str) -> bool:
    """Rough check: does this command shell out to git?"""
    cmd = (command or "").strip().lower()
    return cmd.startswith("git ") or cmd == "git" or " git " in cmd


def _github_git_env(github_token: str) -> Dict[str, str]:
    """Env vars that configure git to use a GitHub token for HTTPS auth.

    We use GIT_ASKPASS trick: set an env var and a small inline script that
    echoes the token when git asks for a password. Also sets
    GIT_CONFIG_COUNT/KEY/VALUE to rewrite github.com URLs to use the token
    (works for both https:// and git@github.com: if they're rewritten to https).
    """
    import tempfile
    # Create an askpass helper once per process, cached at module level
    global _ASKPASS_SCRIPT
    if _ASKPASS_SCRIPT is None or not Path(_ASKPASS_SCRIPT).exists():
        fd, path = tempfile.mkstemp(suffix=".bat" if os.name == "nt" else ".sh", prefix="devforge_askpass_")
        os.close(fd)
        if os.name == "nt":
            # Windows batch: echo the env var content
            Path(path).write_text(
                "@echo off\r\n"
                "echo %DEVFORGE_GIT_TOKEN%\r\n",
                encoding="utf-8"
            )
        else:
            Path(path).write_text(
                '#!/bin/sh\necho "$DEVFORGE_GIT_TOKEN"\n',
                encoding="utf-8"
            )
            os.chmod(path, 0o755)
        _ASKPASS_SCRIPT = path
    return {
        "GIT_ASKPASS": _ASKPASS_SCRIPT,
        "DEVFORGE_GIT_TOKEN": github_token,
        # Also set as username header for GITHUB API calls if needed
        "GITHUB_TOKEN": github_token,
    }


_ASKPASS_SCRIPT: Optional[str] = None


def _is_git_push(command: str) -> bool:
    """Is this specifically a git push command?"""
    cmd = (command or "").strip().lower()
    return cmd.startswith("git push")


async def ensure_git_repo(cwd: Path, github_token: Optional[str] = None) -> list[str]:
    """Ensure the project directory is a git repo with a GitHub remote.

    If not a git repo: init + initial commit.
    If no remote 'origin': create a GitHub repo + add remote.
    Returns a list of log messages describing what was done.
    """
    import subprocess
    logs = []

    # 1. Check if already a git repo
    git_dir = cwd / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=str(cwd), capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(cwd), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit from DevForgeAI"],
            cwd=str(cwd), capture_output=True,
        )
        # Rename branch to main
        subprocess.run(["git", "branch", "-M", "main"], cwd=str(cwd), capture_output=True)
        logs.append("Initialized git repo + initial commit on 'main'")

    # 2. Check if remote 'origin' exists and points to a valid GitHub URL
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=str(cwd), capture_output=True, text=True,
    )
    has_origin = result.returncode == 0
    current_origin = result.stdout.strip() if has_origin else ""

    # If origin exists but doesn't contain github.com, leave it alone (could be GitLab etc.)
    # If it's a github.com URL, verify the repo name matches the project folder
    if has_origin and "github.com" in current_origin and github_token:
        expected_repo = cwd.name
        # Check if the repo name in the URL matches the folder name
        # URL format: https://github.com/user/repo.git
        import re as _re
        url_match = _re.search(r'github\.com[/:][\w-]+/([\w._-]+?)(?:\.git)?$', current_origin)
        if url_match:
            url_repo = url_match.group(1)
            if url_repo != expected_repo:
                # Mismatch — the agent (or a prior auto-setup) set a wrong repo name.
                # Fix it to match the folder name.
                username = _get_github_username(github_token)
                if username:
                    correct_url = f"https://github.com/{username}/{expected_repo}.git"
                    subprocess.run(
                        ["git", "remote", "set-url", "origin", correct_url],
                        cwd=str(cwd), capture_output=True,
                    )
                    current_origin = correct_url
                    logs.append(f"Fixed origin URL: {url_repo} -> {expected_repo}")

    if not has_origin and github_token:
        # Create a GitHub repo named after the project folder
        repo_name = cwd.name
        try:
            import httpx
            # Check if repo exists
            r = httpx.get(
                f"https://api.github.com/repos/{_get_github_username(github_token)}/{repo_name}",
                headers={"Authorization": f"Bearer {github_token}", "Accept": "application/json"},
                timeout=10,
            )
            if r.status_code == 404:
                # Create it
                r = httpx.post(
                    "https://api.github.com/user/repos",
                    headers={
                        "Authorization": f"Bearer {github_token}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json={
                        "name": repo_name,
                        "description": f"Created by DevForgeAI",
                        "private": False,
                        "auto_init": False,
                    },
                    timeout=15,
                )
                if r.status_code == 201:
                    logs.append(f"Created GitHub repo: {r.json().get('html_url')}")
                else:
                    logs.append(f"Failed to create GitHub repo: {r.status_code} {r.text[:100]}")
                    return logs
            elif r.status_code == 200:
                logs.append(f"GitHub repo already exists: {r.json().get('html_url')}")

            # Add remote
            username = _get_github_username(github_token)
            remote_url = f"https://github.com/{username}/{repo_name}.git"
            subprocess.run(
                ["git", "remote", "add", "origin", remote_url],
                cwd=str(cwd), capture_output=True,
            )
            logs.append(f"Added remote origin: {remote_url}")
        except Exception as e:
            logs.append(f"GitHub repo setup failed: {e}")

    return logs


def _get_github_username(github_token: str) -> str:
    """Fetch the GitHub username for a token. Cached."""
    global _CACHED_GH_USERNAME
    if _CACHED_GH_USERNAME:
        return _CACHED_GH_USERNAME
    try:
        import httpx
        r = httpx.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/json"},
            timeout=10,
        )
        if r.status_code == 200:
            _CACHED_GH_USERNAME = r.json().get("login", "")
            return _CACHED_GH_USERNAME
    except Exception:
        pass
    return ""


_CACHED_GH_USERNAME: str = ""


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
    github_token: Optional[str] = None,
) -> Tuple[int, str, str, int]:
    """Run one shell command. Returns (exit_code, stdout, stderr, duration_ms).

    Outputs are truncated to MAX_OUTPUT_BYTES with a "…truncated" tail.
    On timeout, returns (-1, partial_stdout, "Timed out after Xs", duration).

    If github_token is provided AND the command uses git against github.com,
    we inject GitHub credentials via GIT_ASKPASS so `git push` works without
    a personal access token configured.
    """
    started = datetime.utcnow()
    env = {**os.environ}
    # Inject GitHub creds for git operations when we have a token
    if github_token and _is_git_command(command):
        env.update(_github_git_env(github_token))
        # Auto-setup git repo + GitHub remote before push
        if _is_git_push(command):
            try:
                setup_logs = await ensure_git_repo(cwd, github_token)
                for log in setup_logs:
                    logger.info(f"Git auto-setup: {log}")
            except Exception as e:
                logger.warning(f"Git auto-setup failed (continuing anyway): {e}")
            # Try a rebase-pull first to avoid "rejected: fetch first" errors
            # from divergent history (e.g., auto-init created a separate commit tree)
            try:
                import subprocess as _sp
                _sp.run(
                    ["git", "pull", "--rebase", "origin", "main"],
                    cwd=str(cwd), capture_output=True, timeout=30,
                    env=env,  # include GIT_ASKPASS for auth
                )
            except Exception:
                pass  # best-effort; push may still work or fail with a clear error
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env=env,
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
    github_token: Optional[str] = None,
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
    exit_code, stdout, stderr, duration_ms = await run_command(
        command, cwd, timeout_sec=timeout_sec, github_token=github_token
    )
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


def get_first_github_token() -> Optional[str]:
    """Fallback: return the first non-empty github_token from collab_users.json.

    Used when we need a token but don't have a specific user context (e.g.
    pipeline runs are tied to sessions, not users yet). Good enough for
    single-user self-hosted setups.
    """
    import json as _json
    users_file = Path(__file__).parent.parent.parent.parent / "data" / "collab_users.json"
    if not users_file.exists():
        return None
    try:
        users = _json.loads(users_file.read_text(encoding="utf-8"))
        for u in users.values():
            tok = u.get("github_token")
            if tok:
                return tok
    except Exception:
        return None
    return None


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
