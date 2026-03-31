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
from pydantic import BaseModel
from app.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workbench", tags=["workbench"])

# ─── In-memory session store ──────────────────────────────────────────────────
_sessions: Dict[str, Dict[str, Any]] = {}
_queues:   Dict[str, asyncio.Queue]  = {}


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
    if session_id in _queues:
        evt = {"type": type, "payload": payload, "ts": datetime.utcnow().isoformat()}
        try:
            _queues[session_id].put_nowait(evt)
        except asyncio.QueueFull:
            pass


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
async def _resolve_model(model_id: str):
    """Return (Model, Provider) objects from DB for a given model_id string."""
    try:
        from app.database import AsyncSessionLocal
        from app.models.model import Model as ModelORM
        from app.models.provider import Provider as ProviderORM
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ModelORM, ProviderORM)
                .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
                .where(ModelORM.model_id == model_id)
                .limit(1)
            )
            row = result.first()
            if row:
                return row[0], row[1]

            # Fuzzy fallback — partial match
            result = await db.execute(
                select(ModelORM, ProviderORM)
                .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
                .where(ModelORM.model_id.contains(model_id.split("/")[-1]))
                .where(ModelORM.is_active == True)
                .limit(1)
            )
            row = result.first()
            if row:
                return row[0], row[1]

            # Last resort — first active chat model
            result = await db.execute(
                select(ModelORM, ProviderORM)
                .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
                .where(ModelORM.is_active == True)
                .limit(1)
            )
            row = result.first()
            if row:
                return row[0], row[1]
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
_SYSTEM_PROMPT = """You are an expert software engineer. Your job is to implement exactly what the user asks.

Output ONLY the files needed — no prose, no explanation outside the files.
Use this exact format for every file:

FILE: <relative/path/to/file.ext>
```<language>
<complete file content>
```

Rules:
- Every file must be complete and immediately runnable — no placeholders, no TODOs
- Use only standard library + explicitly requested dependencies
- Include a README.md with install and usage instructions
- Do not add files that weren't asked for
- If you think additional files are needed, include them and briefly note why inside the README
"""

async def _real_agent_run(
    session_id: str,
    task: str,
    agent_type: str,
    model_id: str,
    project_path: Optional[Path],
):
    session = _sessions.get(session_id)
    if not session:
        return

    session["status"] = "running"
    session["started_at"] = datetime.utcnow().isoformat()

    _push(session_id, "info", message=f"Starting {agent_type} agent for: \"{task}\"")

    # ── Resolve model ────────────────────────────────────────────────────────
    _push(session_id, "agent_thought", thought=f"Resolving model: {model_id}")
    model_orm, provider_orm = await _resolve_model(model_id)

    if not model_orm:
        _push(session_id, "error", message=f"Could not find model '{model_id}' in database.")
        session["status"] = "failed"
        _push(session_id, "done", message="Session failed.", status="failed")
        return

    _push(session_id, "agent_thought",
          thought=f"Using {model_orm.display_name or model_orm.model_id} via {provider_orm.display_name}")

    # ── Call LLM ─────────────────────────────────────────────────────────────
    _push(session_id, "agent_thought", thought="Generating implementation…")

    from app.services.model_client import ModelClient
    client = ModelClient()

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": task},
    ]

    full_response = ""
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
        async for chunk in stream:
            if session.get("status") == "cancelled":
                break

            # Handle pending user messages mid-stream
            pending = session.get("pending_messages", [])
            if pending:
                for msg in pending:
                    _push(session_id, "user_message", message=msg, handled=True)
                session["pending_messages"] = []

            delta = ""
            try:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta.content or ""
                elif isinstance(chunk, dict):
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            except Exception:
                pass

            if delta:
                full_response += delta
                chunk_count += 1
                # Send a thinking pulse every 20 chunks so the UI shows progress
                if chunk_count % 20 == 0:
                    _push(session_id, "agent_thought",
                          thought=f"Writing… ({len(full_response)} chars so far)")

    except Exception as e:
        logger.error(f"LLM call failed in workbench session {session_id}: {e}")
        _push(session_id, "error", message=f"LLM error: {str(e)}")
        session["status"] = "failed"
        _push(session_id, "done", message="Session failed.", status="failed")
        return

    if session.get("status") == "cancelled":
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

    session["files"] = written
    session["status"] = "completed"
    session["completed_at"] = datetime.utcnow().isoformat()

    location = str(project_path) if project_path else "in-memory only (no project path)"
    _push(session_id, "done",
          message=f"Done. {len(written)} file(s) written to {location}.",
          files_changed=written,
          status="completed")


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/sessions", dependencies=[Depends(verify_api_key)])
async def create_session(body: WorkbenchCreate):
    session_id = str(uuid.uuid4())
    model_id   = body.model or "llama3.1:8b"

    # Resolve project path
    project_path = _resolve_project_path(body.project_id, body.project_path)

    _sessions[session_id] = {
        "id":           session_id,
        "task":         body.task,
        "agent_type":   body.agent_type,
        "model":        model_id,
        "project_id":   body.project_id,
        "project_path": str(project_path) if project_path else None,
        "status":       "pending",
        "created_at":   datetime.utcnow().isoformat(),
        "started_at":   None,
        "completed_at": None,
        "files":        [],
        "pending_messages": [],
    }
    _queues[session_id] = asyncio.Queue(maxsize=1000)

    asyncio.create_task(_real_agent_run(
        session_id, body.task, body.agent_type, model_id, project_path
    ))

    return _sessions[session_id]


@router.get("/sessions", dependencies=[Depends(verify_api_key)])
async def list_sessions():
    return {"data": list(_sessions.values()), "total": len(_sessions)}


@router.get("/sessions/{session_id}", dependencies=[Depends(verify_api_key)])
async def get_session(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return _sessions[session_id]


@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    """SSE stream — no auth header required (EventSource API limitation)."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator() -> AsyncGenerator[str, None]:
        queue = _queues.get(session_id)
        if not queue:
            yield f"data: {json.dumps({'type':'error','payload':{'message':'Queue not found'}})}\n\n"
            return

        # Send current state as first event
        yield f"data: {json.dumps({'type':'init','payload':_sessions[session_id]})}\n\n"

        while True:
            if await request.is_disconnected():
                break
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("type") == "done":
                    s = _sessions.get(session_id, {}).get("status", "")
                    if s != "running":
                        break
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
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    _sessions[session_id].setdefault("pending_messages", []).append(body.message)
    _push(session_id, "user_message", message=body.message, handled=False)
    return {"ok": True}


@router.post("/sessions/{session_id}/cancel", dependencies=[Depends(verify_api_key)])
async def cancel_session(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    _sessions[session_id]["status"] = "cancelled"
    _push(session_id, "info", message="Cancelling…")
    return {"ok": True}


@router.delete("/sessions/{session_id}", dependencies=[Depends(verify_api_key)])
async def delete_session(session_id: str):
    _sessions.pop(session_id, None)
    _queues.pop(session_id, None)
    return {"ok": True}
