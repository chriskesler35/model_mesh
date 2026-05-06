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
    env_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if env_token:
        return env_token

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


# ─── Structured tool executors ────────────────────────────────────────────────
# These are called by the agent runner when a model returns native function-call
# responses (OpenAI tool_calls format).  Each function mirrors a schema defined
# in tool_registry.py and returns a dict with at least "success" and "output".
#
# File-system operations are workspace-bounded: paths outside the project root
# are rejected to prevent accidental writes to system directories.

_MAX_FILE_READ_BYTES = 200 * 1024  # 200 KB cap for read_file
_MAX_LOCAL_FILE_READ_BYTES = 512 * 1024  # 512 KB cap for read_local_file
_MAX_LOCAL_FILE_WRITE_BYTES = 2 * 1024 * 1024  # 2 MB cap for write_local_file

_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".flv"
}
_IMAGE_TARGET_FORMATS = {
    "png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif"
}


def _resolve_workspace_path(relative_path: str, workspace_root: Path) -> Path:
    """Resolve a relative path against the workspace root.

    Raises ValueError if the resolved path escapes the workspace root
    (directory-traversal guard).
    """
    try:
        resolved = (workspace_root / relative_path).resolve()
    except Exception as exc:
        raise ValueError(f"Invalid path: {relative_path}") from exc

    try:
        resolved.relative_to(workspace_root.resolve())
    except ValueError:
        raise ValueError(
            f"Path '{relative_path}' resolves outside the workspace root."
        )

    return resolved


def _resolve_execution_cwd(
    working_directory: Optional[str],
    workspace_root: Path,
) -> Path:
    """Resolve command cwd.

    - If working_directory is omitted, use workspace_root.
    - If absolute, use it directly (supports cross-drive paths on Windows).
    - If relative, resolve from workspace_root.
    """
    base = workspace_root.resolve()
    if not working_directory:
        return base

    raw = str(working_directory).strip()
    candidate = Path(raw).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()

    if not resolved.exists():
        raise ValueError(f"working_directory not found: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"working_directory is not a directory: {resolved}")
    return resolved


def _resolve_local_or_workspace_path(path_value: str, workspace_root: Path) -> Path:
    """Resolve path as absolute local path or workspace-relative path."""
    raw = (path_value or "").strip()
    if not raw:
        raise ValueError("Path is required.")

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return _resolve_workspace_path(raw, workspace_root)


async def tool_read_file(
    path: str,
    workspace_root: Path,
    *,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> dict:
    """Read a file from the workspace and return its contents."""
    try:
        target = _resolve_workspace_path(path, workspace_root)
    except ValueError as exc:
        return {"success": False, "output": str(exc)}

    if not target.exists():
        return {"success": False, "output": f"File not found: {path}"}
    if not target.is_file():
        return {"success": False, "output": f"Path is not a file: {path}"}

    try:
        raw = target.read_bytes()
        if len(raw) > _MAX_FILE_READ_BYTES:
            raw = raw[:_MAX_FILE_READ_BYTES]
            truncated = True
        else:
            truncated = False
        text = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        return {"success": False, "output": f"Read error: {exc}"}

    if start_line is not None or end_line is not None:
        lines = text.splitlines(keepends=True)
        s = max(0, (start_line or 1) - 1)
        e = end_line if end_line is not None else len(lines)
        text = "".join(lines[s:e])

    note = "\n\n[…file truncated at 200 KB…]" if truncated else ""
    return {"success": True, "output": text + note}


async def tool_read_local_file(filepath: str) -> dict:
    """Read a file from an absolute host path (not workspace-bounded)."""
    raw_path = (filepath or "").strip()
    if not raw_path:
        return {"success": False, "output": "filepath is required."}

    try:
        target = Path(raw_path).expanduser().resolve()
    except Exception as exc:
        return {"success": False, "output": f"Invalid filepath: {exc}"}

    if not target.exists():
        return {"success": False, "output": f"File not found: {target}"}
    if not target.is_file():
        return {"success": False, "output": f"Path is not a file: {target}"}

    try:
        raw = target.read_bytes()
        if len(raw) > _MAX_LOCAL_FILE_READ_BYTES:
            raw = raw[:_MAX_LOCAL_FILE_READ_BYTES]
            truncated = True
        else:
            truncated = False
        text = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        return {"success": False, "output": f"Read error: {exc}"}

    note = "\n\n[…file truncated at 512 KB…]" if truncated else ""
    return {
        "success": True,
        "output": text + note,
        "filepath": str(target),
    }


async def tool_write_local_file(filepath: str, content: str) -> dict:
    """Write content to an absolute host path (not workspace-bounded)."""
    raw_path = (filepath or "").strip()
    if not raw_path:
        return {"success": False, "output": "filepath is required."}

    try:
        target = Path(raw_path).expanduser().resolve()
    except Exception as exc:
        return {"success": False, "output": f"Invalid filepath: {exc}"}

    payload = (content or "").encode("utf-8")
    if len(payload) > _MAX_LOCAL_FILE_WRITE_BYTES:
        return {
            "success": False,
            "output": (
                f"Content too large for write_local_file: {len(payload)} bytes "
                f"(max {_MAX_LOCAL_FILE_WRITE_BYTES} bytes)."
            ),
        }

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8")
    except Exception as exc:
        return {"success": False, "output": f"Write error: {exc}"}

    return {
        "success": True,
        "output": f"Wrote {len(payload)} bytes to {target}",
        "filepath": str(target),
    }


async def tool_write_file(
    path: str,
    content: str,
    workspace_root: Path,
    *,
    create_dirs: bool = True,
) -> dict:
    """Write content to a file in the workspace."""
    try:
        target = _resolve_workspace_path(path, workspace_root)
    except ValueError as exc:
        return {"success": False, "output": str(exc)}

    try:
        if create_dirs:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception as exc:
        return {"success": False, "output": f"Write error: {exc}"}

    return {"success": True, "output": f"Wrote {len(content)} chars to {path}"}


async def tool_list_dir(
    path: str,
    workspace_root: Path,
    *,
    recursive: bool = False,
) -> dict:
    """List directory contents in the workspace."""
    try:
        target = _resolve_workspace_path(path, workspace_root)
    except ValueError as exc:
        return {"success": False, "output": str(exc)}

    if not target.exists():
        return {"success": False, "output": f"Path not found: {path}"}
    if not target.is_dir():
        return {"success": False, "output": f"Path is not a directory: {path}"}

    try:
        if recursive:
            entries = sorted(str(p.relative_to(target)) for p in target.rglob("*") if not any(
                part.startswith(".") or part == "__pycache__"
                for part in p.relative_to(target).parts
            ))
        else:
            entries = sorted(
                (p.name + "/" if p.is_dir() else p.name)
                for p in target.iterdir()
            )
    except Exception as exc:
        return {"success": False, "output": f"List error: {exc}"}

    return {"success": True, "output": "\n".join(entries) if entries else "(empty)"}


async def tool_install_package(
    packages: str,
    workspace_root: Path,
    *,
    manager: str = "pip",
    working_directory: Optional[str] = None,
) -> dict:
    """Install packages using the specified package manager."""
    manager = manager.lower().strip()
    pkg_list = packages.strip()

    try:
        exec_cwd = _resolve_execution_cwd(working_directory, workspace_root)
    except ValueError as exc:
        return {"success": False, "output": str(exc)}

    cmd_map = {
        "pip": f"pip install {pkg_list}",
        "npm": f"npm install {pkg_list}",
        "yarn": f"yarn add {pkg_list}",
        "pnpm": f"pnpm add {pkg_list}",
        "cargo": f"cargo add {pkg_list}",
        "go": f"go get {pkg_list}",
    }
    command = cmd_map.get(manager, f"pip install {pkg_list}")

    exit_code, stdout, stderr, duration_ms = await run_command(
        command, exec_cwd, timeout_sec=120
    )
    success = exit_code == 0
    output = stdout if success else (stderr or stdout)
    return {
        "success": success,
        "output": output[:4000],
        "exit_code": exit_code,
        "duration_ms": duration_ms,
    }


async def tool_web_fetch(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[dict] = None,
    body: Optional[str] = None,
) -> dict:
    """Fetch a URL and return the response body."""
    # Basic URL validation — must be http/https
    if not url.lower().startswith(("http://", "https://")):
        return {"success": False, "output": "Only http:// and https:// URLs are supported."}

    try:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            req_headers = dict(headers or {})
            if method.upper() == "POST":
                resp = await client.post(url, headers=req_headers, content=(body or "").encode())
            else:
                resp = await client.get(url, headers=req_headers)

        text = resp.text[:8000]  # cap at 8 KB returned to the model
        return {
            "success": True,
            "output": f"[HTTP {resp.status_code}]\n{text}",
            "status_code": resp.status_code,
        }
    except Exception as exc:
        return {"success": False, "output": f"Fetch error: {exc}"}


async def tool_convert_media(
    source_path: str,
    target_format: str,
    workspace_root: Path,
    *,
    output_path: Optional[str] = None,
    fps: int = 12,
    width: Optional[int] = None,
) -> dict:
    """Convert images between formats or convert video files to GIF."""
    try:
        src = _resolve_local_or_workspace_path(source_path, workspace_root)
    except ValueError as exc:
        return {"success": False, "output": str(exc)}

    if not src.exists() or not src.is_file():
        return {"success": False, "output": f"Source file not found: {src}"}

    fmt = (target_format or "").strip().lower().lstrip(".")
    if not fmt:
        return {"success": False, "output": "target_format is required."}

    if output_path:
        try:
            out = _resolve_local_or_workspace_path(output_path, workspace_root)
        except ValueError as exc:
            return {"success": False, "output": str(exc)}
    else:
        out = src.with_suffix(f".{fmt}")

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return {"success": False, "output": f"Failed to create output directory: {exc}"}

    src_ext = src.suffix.lower()
    is_video = src_ext in _VIDEO_EXTENSIONS

    if is_video:
        if fmt != "gif":
            return {
                "success": False,
                "output": "Video conversion currently supports target_format='gif' only.",
            }

        gif_fps = fps if isinstance(fps, int) and fps > 0 else 12
        vf_parts = [f"fps={gif_fps}"]
        if isinstance(width, int) and width > 0:
            vf_parts.append(f"scale={width}:-1:flags=lanczos")
        vf = ",".join(vf_parts)

        command = f'ffmpeg -y -i "{src}" -vf "{vf}" "{out}"'
        exit_code, stdout, stderr, _ = await run_command(command, workspace_root, timeout_sec=600)
        if exit_code != 0:
            return {
                "success": False,
                "output": (
                    "ffmpeg conversion failed. Ensure ffmpeg is installed and on PATH.\n"
                    f"{stderr or stdout}"
                )[:5000],
            }

        return {
            "success": True,
            "output": f"Converted video to GIF: {out}",
            "source_path": str(src),
            "output_path": str(out),
        }

    if fmt not in _IMAGE_TARGET_FORMATS:
        return {
            "success": False,
            "output": f"Unsupported image target format: {fmt}",
        }

    try:
        from PIL import Image
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except Exception:
            # HEIC conversion will fail naturally below if HEIF support is unavailable.
            pass

        with Image.open(src) as img:
            save_kwargs = {}
            if fmt in {"jpg", "jpeg"}:
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                save_kwargs["quality"] = 92
            img.save(out, format=fmt.upper(), **save_kwargs)
    except Exception as exc:
        return {
            "success": False,
            "output": (
                "Image conversion failed. For HEIC sources, install pillow-heif. "
                f"Details: {exc}"
            )[:5000],
        }

    return {
        "success": True,
        "output": f"Converted image to .{fmt}: {out}",
        "source_path": str(src),
        "output_path": str(out),
    }


async def execute_tool_call(
    tool_name: str,
    arguments: dict,
    workspace_root: Path,
) -> dict:
    """Dispatch a native function-call tool request to the correct executor.

    Returns a result dict with at least ``success`` (bool) and ``output`` (str).
    This is the single entry point used by AgentRunner when a model returns
    an OpenAI-style tool_calls response.
    """
    name = (tool_name or "").strip()

    if name == "read_file":
        return await tool_read_file(
            path=arguments.get("path", ""),
            workspace_root=workspace_root,
            start_line=arguments.get("start_line"),
            end_line=arguments.get("end_line"),
        )

    if name == "read_local_file":
        return await tool_read_local_file(
            filepath=arguments.get("filepath", ""),
        )

    if name == "write_local_file":
        return await tool_write_local_file(
            filepath=arguments.get("filepath", ""),
            content=arguments.get("content", ""),
        )

    if name == "write_file":
        return await tool_write_file(
            path=arguments.get("path", ""),
            content=arguments.get("content", ""),
            workspace_root=workspace_root,
            create_dirs=arguments.get("create_dirs", True),
        )

    if name == "list_dir":
        return await tool_list_dir(
            path=arguments.get("path", "."),
            workspace_root=workspace_root,
            recursive=arguments.get("recursive", False),
        )

    if name == "run_shell":
        command = arguments.get("command", "")
        timeout = int(arguments.get("timeout") or 60)
        working_directory = arguments.get("working_directory")
        from app.services.command_classifier import classify_command, CommandTier
        tier = classify_command(command)
        if tier == CommandTier.BLOCKED:
            return {"success": False, "output": "Command blocked by sandbox policy."}

        try:
            exec_cwd = _resolve_execution_cwd(working_directory, workspace_root)
        except ValueError as exc:
            return {"success": False, "output": str(exc)}

        exit_code, stdout, stderr, duration_ms = await run_command(
            command, exec_cwd, timeout_sec=timeout
        )
        success = exit_code == 0
        return {
            "success": success,
            "output": (stdout or "") + ("\n" + stderr if stderr else ""),
            "exit_code": exit_code,
            "duration_ms": duration_ms,
        }

    if name == "install_package":
        return await tool_install_package(
            packages=arguments.get("packages", ""),
            workspace_root=workspace_root,
            manager=arguments.get("manager", "pip"),
            working_directory=arguments.get("working_directory"),
        )

    if name == "web_fetch":
        return await tool_web_fetch(
            url=arguments.get("url", ""),
            method=arguments.get("method", "GET"),
            headers=arguments.get("headers"),
            body=arguments.get("body"),
        )

    if name == "convert_media":
        return await tool_convert_media(
            source_path=arguments.get("source_path", ""),
            target_format=arguments.get("target_format", ""),
            workspace_root=workspace_root,
            output_path=arguments.get("output_path"),
            fps=int(arguments.get("fps") or 12),
            width=arguments.get("width"),
        )

    return {"success": False, "output": f"Unknown tool: {name}"}
