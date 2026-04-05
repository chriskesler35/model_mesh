"""Live Development Workbench — real LLM agent that writes files to disk."""

import uuid
import json
import asyncio
import logging
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, AsyncGenerator
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from app.middleware.auth import verify_api_key
from app.database import get_db, AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workbench", tags=["workbench"])

# ─── In-memory queues (SSE streaming only — sessions persisted to DB) ─────────
_queues:            Dict[str, asyncio.Queue]  = {}
_pending_messages:  Dict[str, list]           = {}
_event_logs:        Dict[str, list]           = {}  # full event log per session for DB persistence/replay


# ─── Schemas ──────────────────────────────────────────────────────────────────
class WorkbenchCreate(BaseModel):
    task: str
    agent_type: str = "coder"
    model: Optional[str] = None
    project_path: Optional[str] = None
    project_id: Optional[str] = None


class WorkbenchMessage(BaseModel):
    message: str


# ─── Event helpers ────────────────────────────────────────────────────────────
def _push(session_id: str, type: str, **payload):
    evt = {"type": type, "payload": payload, "ts": datetime.utcnow().isoformat()}
    # Persist to in-memory event log for DB replay (capped at 500 events/session)
    log = _event_logs.setdefault(session_id, [])
    log.append(evt)
    if len(log) > 500:
        del log[0:len(log) - 500]
    # Push to live SSE queue if any subscribers
    if session_id in _queues:
        try:
            _queues[session_id].put_nowait(evt)
        except asyncio.QueueFull:
            pass


async def _db_update(session_id: str, **kwargs):
    """Update the persisted session record in DB."""
    try:
        from app.models.workbench import WorkbenchSession
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(WorkbenchSession).where(WorkbenchSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if session:
                for k, v in kwargs.items():
                    setattr(session, k, v)
                await db.commit()
    except Exception as e:
        logger.warning(f"DB update failed for workbench session {session_id}: {e}")


# ─── Project path resolver ────────────────────────────────────────────────────
def _resolve_project_path(project_id: Optional[str], project_path: Optional[str]) -> Optional[Path]:
    """Look up project path from projects.json or use the provided path directly."""
    if project_path:
        return Path(project_path)
    if project_id:
        try:
            from pathlib import Path as P
            data_dir = P(__file__).parent.parent.parent.parent / "data"
            pf = data_dir / "projects.json"
            if pf.exists():
                projects = json.loads(pf.read_text(encoding="utf-8"))
                proj = projects.get(project_id)
                if proj and proj.get("path"):
                    return Path(proj["path"])
        except Exception as e:
            logger.warning(f"Could not resolve project path for {project_id}: {e}")
    return None


# ─── LLM model resolver ───────────────────────────────────────────────────────
def _provider_has_credentials(provider_name: str) -> bool:
    """Check if a provider has API credentials available (Ollama/local always true)."""
    p = (provider_name or "").lower()
    if p in ("ollama", "local", "lm-studio", "lmstudio", "llamacpp"):
        return True
    if p == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if p == "google":
        return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if p == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    if p == "openrouter":
        return bool(os.environ.get("OPENROUTER_API_KEY"))
    # Unknown providers — assume yes and let the call fail loudly
    return True


async def _resolve_model(model_id: str):
    """Return (Model, Provider) objects from DB for a given model_id string.

    Never silently falls back to a model whose provider has no credentials —
    surfaces the failure so the caller can report the real problem.
    """
    try:
        from app.database import AsyncSessionLocal
        from app.models.model import Model as ModelORM
        from app.models.provider import Provider as ProviderORM
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            # 1. Exact match on model_id
            result = await db.execute(
                select(ModelORM, ProviderORM)
                .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
                .where(ModelORM.model_id == model_id)
                .limit(1)
            )
            row = result.first()
            if row:
                if not _provider_has_credentials(row[1].name):
                    logger.error(f"Model '{model_id}' matched but provider '{row[1].name}' has no API credentials set")
                    return None, None
                return row[0], row[1]

            # 2. Fuzzy partial match — ONLY keep candidates whose provider has credentials
            last_part = model_id.split("/")[-1]
            result = await db.execute(
                select(ModelORM, ProviderORM)
                .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
                .where(ModelORM.model_id.contains(last_part))
                .where(ModelORM.is_active == True)
            )
            for m, p in result:
                if _provider_has_credentials(p.name):
                    logger.info(f"Model '{model_id}' fuzzy-matched to '{m.model_id}' via {p.name}")
                    return m, p

            # No fallback to arbitrary models — return None so the caller surfaces the error
            logger.error(f"Could not resolve model '{model_id}' to any provider with credentials")
    except Exception as e:
        logger.error(f"Model resolve failed: {e}")
    return None, None


# ─── File parser ──────────────────────────────────────────────────────────────
def _parse_files(text: str) -> list[dict]:
    """
    Extract files from LLM output.

    Supported formats (tried in order):

    Format 1 — FILE: marker (most reliable, what we ask for in system prompt):
        FILE: path/to/file.ext
        ```lang
        content
        ```

    Format 2 — fenced block with filename tag:
        ```python filename: bench.py
        content
        ```

    Format 3 — markdown header with filename:
        ### bench.py
        ```python
        content
        ```
    """
    files = []

    # Format 1 — FILE: marker
    # Use split-based approach instead of regex to handle edge cases reliably
    # Split on FILE: markers (case-insensitive), handling both start-of-string and newline-preceded
    parts = re.split(r'(?:^|\n)(?:FILE|file):\s*', text)
    for part in parts[1:]:  # skip first chunk (before first FILE:)
        lines = part.split('\n')
        path = lines[0].strip()
        rest = '\n'.join(lines[1:])

        # Find the code block
        block_match = re.search(r'```[^\n]*\n(.*?)(?:```|$)', rest, re.DOTALL)
        if block_match and path:
            content = block_match.group(1)
            # Strip trailing ``` if present
            content = re.sub(r'\s*```\s*$', '', content)
            files.append({"path": path, "content": content})

    if files:
        return files

    # Format 2 — ```lang filename: path
    pattern2 = re.compile(
        r'```[\w]*\s+(?:filename:|file:)\s*(\S+)\s*\n(.*?)```',
        re.DOTALL | re.IGNORECASE
    )
    for m in pattern2.finditer(text):
        files.append({"path": m.group(1).strip(), "content": m.group(2)})

    if files:
        return files

    # Format 3 — ### filename.ext header
    pattern3 = re.compile(
        r'#{1,4}\s+`?([^\n`]+\.\w+)`?\s*\n+```[^\n]*\n(.*?)```',
        re.DOTALL
    )
    for m in pattern3.finditer(text):
        fname = m.group(1).strip()
        if len(fname) < 120:
            files.append({"path": fname, "content": m.group(2)})

    return files


# ─── Real agent runner ────────────────────────────────────────────────────────
_BASE_SYSTEM_PROMPT = """You are an expert software engineer working iteratively with a user on a project.

You work one turn at a time. Each turn the user gives you a task or refinement, and you either:
  (a) write/modify files to accomplish it, OR
  (b) ask a clarifying question if the request is ambiguous.

IMPORTANT: Start EVERY response with a single line declaring your current role for this turn:
ROLE: <one of: Analyst, Planner, Architect, Coder, Reviewer, Tester, Researcher>

Pick the role that best fits what this turn needs. For a fresh implementation task you're usually "Coder".
For a fuzzy request that needs clarification, you're "Analyst". When designing structure before coding, "Architect".

After the ROLE line, write file blocks in this EXACT format:

FILE: <relative/path/to/file.ext>
```<language>
<complete file content>
```

Rules for file output:
- Every file must be complete and immediately runnable — no placeholders, no TODOs
- Use only standard library + dependencies that are already in the project OR explicitly requested
- If the user's request implies new dependencies, include an updated requirements.txt / package.json
- Include or update README.md so it always reflects current install + usage instructions
- Only write files you're actually changing; don't rewrite untouched files
- After the file blocks, add a brief summary (2-4 lines) of WHAT you changed and WHY

If the user's request is genuinely unclear and you cannot make a sensible assumption,
respond with a short clarifying question INSTEAD of file blocks. Do not do both.

CONTEXT: You will see the current state of the project (existing files) in the conversation.
Read them carefully before deciding what to change. Prefer minimal, focused edits over rewrites.
"""


def _get_active_method_prompt() -> tuple[str, list]:
    """Read active development method and return (extra_system_prompt, phase_list)."""
    try:
        from app.routes.methods import _load_state, BUILT_IN_METHODS
        state = _load_state()
        method = BUILT_IN_METHODS.get(state.get("active_method", "standard"), BUILT_IN_METHODS["standard"])
        return method.get("system_prompt", ""), method.get("phases", [])
    except Exception:
        return "", []


def _parse_role(response: str) -> Optional[str]:
    """Extract the ROLE: <name> declaration from the start of an agent response."""
    match = re.match(r'^\s*ROLE:\s*([A-Za-z][A-Za-z ]{0,30})', response)
    if match:
        return match.group(1).strip()
    return None


def _read_project_snapshot(project_path: Optional[Path], max_files: int = 40, max_bytes_per_file: int = 8000) -> str:
    """Read the current project files and return a formatted snapshot for the LLM."""
    if not project_path or not project_path.exists():
        return "(no existing files — this is a fresh project)"

    # Skip directories that will blow up context
    skip_dirs = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".pytest_cache"}
    skip_suffixes = {".pyc", ".lock", ".log", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".zip", ".tar", ".gz"}

    files_content = []
    file_count = 0
    for p in sorted(project_path.rglob("*")):
        if file_count >= max_files:
            files_content.append(f"\n… and more (showing first {max_files} files only)")
            break
        if not p.is_file():
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        if p.suffix.lower() in skip_suffixes:
            continue
        try:
            rel = p.relative_to(project_path).as_posix()
        except ValueError:
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if len(content) > max_bytes_per_file:
            content = content[:max_bytes_per_file] + f"\n… (truncated, {len(content) - max_bytes_per_file} more bytes)"
        files_content.append(f"--- FILE: {rel} ---\n{content}")
        file_count += 1

    if not files_content:
        return "(project folder exists but is empty)"

    return f"# Current project state ({project_path.name}):\n\n" + "\n\n".join(files_content)

async def _run_turn(
    session_id: str,
    user_message: str,
    agent_type: str,
    model_id: str,
    project_path: Optional[Path],
    history: list,  # prior [{role, content}] messages (minus system)
):
    """Run ONE conversational turn with the agent.

    After completing, status is set to 'waiting' so the user can send another
    follow-up message. Each turn reads the current project files as context
    so the agent can iterate on what's already on disk.
    """
    started = datetime.utcnow()
    await _db_update(session_id, status="running", started_at=started)
    turn_num = (len([m for m in history if m.get("role") == "user"]) + 1)
    _push(session_id, "info", message=f"Turn {turn_num}: {user_message[:80]}{'…' if len(user_message) > 80 else ''}")

    # ── Resolve model ────────────────────────────────────────────────────────
    model_orm, provider_orm = await _resolve_model(model_id)

    if not model_orm:
        _push(session_id, "error", message=f"Could not find model '{model_id}' in database.")
        await _db_update(session_id, status="failed", completed_at=datetime.utcnow())
        _push(session_id, "done", message="Session failed.", status="failed")
        return

    _push(session_id, "agent_thought",
          thought=f"Reading project files and thinking with {model_orm.display_name or model_orm.model_id}…")

    # ── Build message list: base system + method prompt + history + snapshot + user
    from app.services.model_client import ModelClient
    client = ModelClient()

    snapshot = _read_project_snapshot(project_path)

    # Compose system prompt: base + identity/soul/user + active method
    from app.services.identity_context import build_identity_context
    identity_block = build_identity_context(include_method=True)
    method_prompt, method_phases = _get_active_method_prompt()

    system_prompt = _BASE_SYSTEM_PROMPT
    if identity_block:
        system_prompt = f"{identity_block}\n\n---\n\n{_BASE_SYSTEM_PROMPT}"
    if method_phases:
        phase_list = ", ".join(method_phases)
        system_prompt += f"\n\n**Method phases available:** {phase_list}. Use these as your ROLE when fitting."
        _push(session_id, "info", message=f"Method phases: {phase_list}")

    messages = [{"role": "system", "content": system_prompt}]
    # Keep the last 6 user+assistant pairs to cap context growth
    recent_history = history[-12:] if len(history) > 12 else history
    messages.extend(recent_history)
    # Inject the current file snapshot + new user request
    messages.append({
        "role": "user",
        "content": f"{snapshot}\n\n---\n\nUser request for this turn: {user_message}"
    })

    full_response = ""
    input_tokens = 0
    output_tokens = 0
    llm_start = datetime.utcnow()
    llm_success = True
    llm_error = None

    try:
        stream = await client.call_model(
            model=model_orm,
            provider=provider_orm,
            messages=messages,
            stream=True,
            temperature=0.2,
            max_tokens=8000,
        )

        chunk_count = 0
        role_pushed = False
        async for chunk in stream:
            if _pending_messages.get(session_id) == "cancelled":
                break

            # Handle pending user messages mid-stream
            pending = _pending_messages.get(session_id, [])
            if isinstance(pending, list) and pending:
                for msg in pending:
                    _push(session_id, "user_message", message=msg, handled=True)
                _pending_messages[session_id] = []

            delta = ""
            try:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta.content or ""
                elif isinstance(chunk, dict):
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            except Exception:
                pass

            # Capture token usage from final chunk (LiteLLM streams usage on last chunk)
            try:
                usage = None
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = chunk.usage
                elif isinstance(chunk, dict) and chunk.get("usage"):
                    usage = chunk["usage"]
                if usage:
                    input_tokens = getattr(usage, "prompt_tokens", 0) or (usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0)
                    output_tokens = getattr(usage, "completion_tokens", 0) or (usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0)
            except Exception:
                pass

            if delta:
                full_response += delta
                chunk_count += 1
                # Detect ROLE declaration as soon as first line lands, push once
                if chunk_count < 30 and "\n" in full_response and not role_pushed:
                    parsed_role = _parse_role(full_response)
                    if parsed_role:
                        _push(session_id, "role_change", role=parsed_role)
                        role_pushed = True
                if chunk_count % 20 == 0:
                    _push(session_id, "agent_thought",
                          thought=f"Writing. ({len(full_response)} chars so far)")

    except Exception as e:
        logger.error(f"LLM call failed in workbench session {session_id}: {e}")
        llm_success = False
        llm_error = str(e)
        _push(session_id, "error", message=f"LLM error: {str(e)}")
        await _db_update(session_id, status="failed", completed_at=datetime.utcnow())
        _push(session_id, "done", message="Session failed.", status="failed")

    # Estimate tokens if stream did not return usage
    if input_tokens == 0:
        input_tokens = client.estimate_tokens(messages, model_orm)
    if output_tokens == 0 and full_response:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            output_tokens = len(enc.encode(full_response))
        except Exception:
            output_tokens = len(full_response) // 4

    # Estimate cost
    estimated_cost = client.estimate_cost(input_tokens, output_tokens, model_orm)

    # Write to request_logs so Stats picks it up
    latency_ms = int((datetime.utcnow() - llm_start).total_seconds() * 1000)
    try:
        from app.models.request_log import RequestLog
        async with AsyncSessionLocal() as db:
            log = RequestLog(
                model_id=str(model_orm.id),
                provider_id=str(provider_orm.id),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                estimated_cost=estimated_cost,
                success=llm_success,
                error_message=llm_error,
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to write request_log for workbench session {session_id}: {e}")

    # Persist token/cost + event log to workbench session record
    await _db_update(
        session_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=estimated_cost,
        events_log=_event_logs.get(session_id, []),
    )

    if not llm_success:
        return

    if _pending_messages.get(session_id) == "cancelled":
        await _db_update(session_id, status="cancelled", completed_at=datetime.utcnow())
        _push(session_id, "info", message="Session cancelled.")
        _push(session_id, "done", message="Session cancelled.", status="cancelled")
        return

    # ── Parse files ──────────────────────────────────────────────────────────
    _push(session_id, "agent_thought", thought="Parsing generated files…")

    # Log first 2000 chars of raw response for debugging
    logger.info(f"Workbench raw response ({len(full_response)} chars):\n{full_response[:2000]}")

    files = _parse_files(full_response)

    if not files:
        # No structured files found — save entire response as output.md
        files = [{"path": "output.md", "content": full_response}]
        _push(session_id, "agent_thought",
              thought="No FILE: blocks detected — saving full response as output.md")

    # ── Write files to disk ──────────────────────────────────────────────────
    written = []
    for f in files:
        rel_path = f["path"].lstrip("/\\")
        content  = f["content"]

        _push(session_id, "agent_thought", thought=f"Writing {rel_path}…")

        if project_path:
            abs_path = project_path / rel_path
            try:
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(content, encoding="utf-8")
                _push(session_id, "file_created", path=rel_path,
                      content=content[:500] + ("…" if len(content) > 500 else ""))
                written.append(rel_path)
                logger.info(f"Workbench wrote: {abs_path}")
            except Exception as e:
                _push(session_id, "error", message=f"Failed to write {rel_path}: {e}")
        else:
            # No project path — emit the content so frontend can display it
            _push(session_id, "file_created", path=rel_path,
                  content=content[:500] + ("…" if len(content) > 500 else ""),
                  note="No project path set — file not saved to disk")
            written.append(rel_path)

        await asyncio.sleep(0.1)  # brief yield so SSE stream flushes

    # Extract the text that followed the file blocks as agent commentary
    # Strip FILE: blocks AND the ROLE: line out of full_response
    commentary = re.sub(r'FILE:[^\n]*\n```[^\n]*\n.*?```', '', full_response, flags=re.DOTALL)
    commentary = re.sub(r'^\s*ROLE:\s*[A-Za-z][A-Za-z ]*\n', '', commentary).strip()
    if not commentary and written:
        commentary = f"Wrote {len(written)} file(s): {', '.join(written)}"
    elif not commentary:
        commentary = full_response[:500]

    # Build new conversation history for this turn
    new_history = list(history) + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": full_response},
    ]

    # Accumulate all files ever written across turns (union)
    prior_files = []
    try:
        from app.models.workbench import WorkbenchSession
        async with AsyncSessionLocal() as db:
            row = await db.execute(select(WorkbenchSession).where(WorkbenchSession.id == session_id))
            sess = row.scalar_one_or_none()
            if sess and sess.files:
                prior_files = sess.files
    except Exception:
        pass
    all_files = list(dict.fromkeys((prior_files or []) + written))

    # After a turn, go to 'waiting' status — user can send a follow-up
    completed = datetime.utcnow()
    await _db_update(
        session_id,
        status="waiting",
        completed_at=completed,
        files=all_files,
        messages=new_history,
    )

    location = str(project_path) if project_path else "in-memory only (no project path)"
    _push(session_id, "agent_reply", message=commentary, files_changed=written)
    _push(session_id, "done",
          message=f"Turn {turn_num} complete. {len(written)} file(s) updated in {location}. Send a follow-up to continue.",
          files_changed=written,
          status="waiting")


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/sessions", dependencies=[Depends(verify_api_key)])
async def create_session(body: WorkbenchCreate, db: AsyncSession = Depends(get_db)):
    from app.models.workbench import WorkbenchSession
    session_id = str(uuid.uuid4())
    model_id   = body.model or "llama3.1:8b"
    project_path = _resolve_project_path(body.project_id, body.project_path)

    # Persist to DB
    session = WorkbenchSession(
        id=session_id,
        task=body.task,
        agent_type=body.agent_type,
        model=model_id,
        project_id=body.project_id,
        project_path=str(project_path) if project_path else None,
        status="pending",
        files=[],
    )
    db.add(session)
    await db.commit()

    # Set up SSE queue
    _queues[session_id] = asyncio.Queue(maxsize=1000)
    _pending_messages[session_id] = []

    # Kick off the first turn with the initial task
    asyncio.create_task(_run_turn(
        session_id=session_id,
        user_message=body.task,
        agent_type=body.agent_type,
        model_id=model_id,
        project_path=project_path,
        history=[],
    ))

    return session.to_dict()


@router.get("/sessions", dependencies=[Depends(verify_api_key)])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    from app.models.workbench import WorkbenchSession
    result = await db.execute(
        select(WorkbenchSession).order_by(desc(WorkbenchSession.created_at)).limit(100)
    )
    sessions = result.scalars().all()
    return {"data": [s.to_dict() for s in sessions], "total": len(sessions)}


@router.get("/sessions/{session_id}", dependencies=[Depends(verify_api_key)])
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.workbench import WorkbenchSession
    result = await db.execute(
        select(WorkbenchSession).where(WorkbenchSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_dict()


@router.get("/sessions/{session_id}/files/read", dependencies=[Depends(verify_api_key)])
async def read_session_file(session_id: str, path: str, db: AsyncSession = Depends(get_db)):
    """Read a file the agent wrote into the session's project directory."""
    from app.models.workbench import WorkbenchSession
    result = await db.execute(
        select(WorkbenchSession).where(WorkbenchSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.project_path:
        raise HTTPException(status_code=404, detail="Session has no project path (file not on disk)")

    root = Path(session.project_path).resolve()
    target = (root / path.lstrip("/\\")).resolve()

    # Security: file must live under the session's project root
    if not str(target).startswith(str(root)):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found on disk")
    if target.stat().st_size > 500_000:
        raise HTTPException(status_code=413, detail="File too large to preview (>500KB)")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content, "size": target.stat().st_size}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    """SSE stream — no auth header required (EventSource API limitation)."""
    from app.models.workbench import WorkbenchSession
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorkbenchSession).where(WorkbenchSession.id == session_id)
        )
        session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        queue = _queues.get(session_id)
        if not queue:
            # Session exists in DB but not actively running - replay stored events
            session_dict = session.to_dict()
            yield f"data: {json.dumps({'type':'init','payload':session_dict})}\n\n"
            for evt in (session_dict.get('events_log') or []):
                yield f"data: {json.dumps(evt)}\n\n"
                import asyncio as _asyncio; await _asyncio.sleep(0.02)
            log_types = [e.get('type') for e in (session_dict.get('events_log') or [])]
            if 'done' not in log_types:
                yield f"data: {json.dumps({'type':'done','payload':{'message':'Session ' + session.status, 'status':session.status}})}\n\n"
            return

        yield f"data: {json.dumps({'type':'init','payload':session.to_dict()})}\n\n"

        while True:
            if await request.is_disconnected():
                break
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(evt)}\n\n"
                # Only close the stream on terminal statuses. 'waiting' means
                # the session stays open for follow-up turns.
                if evt.get("type") == "done":
                    final_status = (evt.get("payload") or {}).get("status", "")
                    if final_status in ("completed", "failed", "cancelled", "error"):
                        break
                    # status == "waiting" → keep streaming for next turn
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type':'ping','payload':{}})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":       "no-cache",
            "X-Accel-Buffering":   "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


@router.post("/sessions/{session_id}/message", dependencies=[Depends(verify_api_key)])
async def send_message(session_id: str, body: WorkbenchMessage):
    """Send a follow-up message — starts a new agent turn on the same session."""
    from app.models.workbench import WorkbenchSession
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorkbenchSession).where(WorkbenchSession.id == session_id)
        )
        session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status == "running":
        raise HTTPException(status_code=409, detail="Agent is still working on the previous turn — wait for it to finish")

    # Recreate SSE queue if session was previously idle
    if session_id not in _queues:
        _queues[session_id] = asyncio.Queue(maxsize=1000)

    _push(session_id, "user_message", message=body.message, handled=True)

    # Kick off a new turn with full conversation history
    history = session.messages or []
    project_path = Path(session.project_path) if session.project_path else None

    asyncio.create_task(_run_turn(
        session_id=session_id,
        user_message=body.message,
        agent_type=session.agent_type or "coder",
        model_id=session.model or "llama3.1:8b",
        project_path=project_path,
        history=history,
    ))
    return {"ok": True, "turn": len(history) // 2 + 1}


@router.post("/sessions/{session_id}/cancel", dependencies=[Depends(verify_api_key)])
async def cancel_session(session_id: str):
    _pending_messages[session_id] = "cancelled"
    _push(session_id, "info", message="Cancelling…")
    await _db_update(session_id, status="cancelled", completed_at=datetime.utcnow())
    return {"ok": True}


@router.delete("/sessions/{session_id}", dependencies=[Depends(verify_api_key)])
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.workbench import WorkbenchSession
    result = await db.execute(
        select(WorkbenchSession).where(WorkbenchSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)
        await db.commit()
    _queues.pop(session_id, None)
    _pending_messages.pop(session_id, None)
    _event_logs.pop(session_id, None)
    return {"ok": True}


@router.delete("/sessions", dependencies=[Depends(verify_api_key)])
async def delete_all_sessions(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Bulk-delete workbench sessions AND their attached pipelines.

    Optional ?status=completed|failed|cancelled|waiting filter — if omitted,
    deletes every non-running session. Running sessions are preserved unless
    the status filter explicitly selects them.
    """
    from app.models.workbench import WorkbenchSession
    from app.models.pipeline import Pipeline, PhaseRun

    query = select(WorkbenchSession)
    if status:
        query = query.where(WorkbenchSession.status == status)
    else:
        # Default: everything except currently-running
        query = query.where(WorkbenchSession.status != "running")

    sessions = (await db.execute(query)).scalars().all()
    session_ids = [s.id for s in sessions]

    # Collect attached pipelines + phase runs so they cascade-clean too
    deleted_pipelines = 0
    deleted_phase_runs = 0
    if session_ids:
        # Delete phase_runs via their pipelines' session_ids
        pipelines = (await db.execute(
            select(Pipeline).where(Pipeline.session_id.in_(session_ids))
        )).scalars().all()
        for p in pipelines:
            phase_runs = (await db.execute(
                select(PhaseRun).where(PhaseRun.pipeline_id == p.id)
            )).scalars().all()
            for pr in phase_runs:
                await db.delete(pr)
                deleted_phase_runs += 1
            await db.delete(p)
            deleted_pipelines += 1

        for s in sessions:
            await db.delete(s)
            # Clean up in-memory state
            _queues.pop(s.id, None)
            _pending_messages.pop(s.id, None)
            _event_logs.pop(s.id, None)

        await db.commit()

    return {
        "ok": True,
        "deleted_sessions": len(session_ids),
        "deleted_pipelines": deleted_pipelines,
        "deleted_phase_runs": deleted_phase_runs,
    }
