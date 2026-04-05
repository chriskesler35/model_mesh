"""Multi-agent pipeline orchestration (Option A).

A Pipeline runs a task through N specialist phases (Analyst → Architect →
Coder → Reviewer → ...). Each phase is one LLM call with its own role,
system prompt, and structured artifact output. Phases gate on user approval
between runs (unless auto_approve=True).

Architecture:
  - One workbench_session owns the pipeline (via session.pipeline_id)
  - Each phase is a PhaseRun row (persisted for audit + replay)
  - Prior phase artifacts are injected as context for downstream phases
  - SSE events stream to the frontend via the pipeline's own event queue
  - Approval endpoints advance the pipeline; rejection re-runs the current phase
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.middleware.auth import verify_api_key
from app.database import get_db, AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workbench/pipelines", tags=["pipelines"])


# ─── In-memory event queues for SSE (state lives in DB) ───────────────────────
_queues:     Dict[str, asyncio.Queue] = {}
_event_logs: Dict[str, List[dict]]    = {}


# ─── Schemas ──────────────────────────────────────────────────────────────────
class PipelineCreate(BaseModel):
    session_id: str
    method_id: str                              # 'bmad' | 'gsd' | 'superpowers'
    task: str
    auto_approve: bool = False
    model_overrides: Optional[Dict[str, str]] = None   # {phase_name: model_id}


class PipelineApprove(BaseModel):
    feedback: Optional[str] = None


class PipelineReject(BaseModel):
    feedback: str                                # required — why we're rejecting


class PipelineSkip(BaseModel):
    reason: Optional[str] = None


# ─── Event helpers ────────────────────────────────────────────────────────────
def _push(pipeline_id: str, type: str, **payload):
    evt = {"type": type, "payload": payload, "ts": datetime.utcnow().isoformat()}
    log = _event_logs.setdefault(pipeline_id, [])
    log.append(evt)
    if len(log) > 500:
        del log[0:len(log) - 500]
    q = _queues.get(pipeline_id)
    if q:
        try:
            q.put_nowait(evt)
        except asyncio.QueueFull:
            pass


async def _db_update_pipeline(pipeline_id: str, **kwargs):
    from app.models.pipeline import Pipeline
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
            p = result.scalar_one_or_none()
            if p:
                for k, v in kwargs.items():
                    setattr(p, k, v)
                await db.commit()
    except Exception as e:
        logger.warning(f"Pipeline DB update failed for {pipeline_id}: {e}")


async def _db_update_phase(phase_run_id: str, **kwargs):
    from app.models.pipeline import PhaseRun
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(PhaseRun).where(PhaseRun.id == phase_run_id))
            pr = result.scalar_one_or_none()
            if pr:
                for k, v in kwargs.items():
                    setattr(pr, k, v)
                await db.commit()
    except Exception as e:
        logger.warning(f"PhaseRun DB update failed for {phase_run_id}: {e}")


# ─── Artifact extractors ──────────────────────────────────────────────────────
def _extract_json_artifact(text: str) -> Optional[dict]:
    """Pull the first ```json ... ``` block out of an LLM response."""
    m = re.search(r'```json\s*\n(.*?)```', text, re.DOTALL)
    if not m:
        # fallback — any fenced block that parses as JSON
        m = re.search(r'```[a-z]*\s*\n(\{.*?\}|\[.*?\])\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception as e:
            logger.debug(f"JSON parse failed: {e}")
            # Try to find a bare JSON object
            try:
                m2 = re.search(r'(\{[\s\S]*\})', text)
                if m2:
                    return json.loads(m2.group(1))
            except Exception:
                pass
    return None


def _extract_code_files(text: str) -> List[dict]:
    """Reuse the workbench FILE: parser to extract code files."""
    from app.routes.workbench import _parse_files
    return _parse_files(text)


def _build_artifact(phase_def: dict, raw_response: str) -> dict:
    """Convert raw LLM text into the structured artifact for this phase type."""
    atype = phase_def.get("artifact_type", "md")
    if atype == "json":
        data = _extract_json_artifact(raw_response)
        return {"type": "json", "data": data, "raw": raw_response}
    elif atype == "code":
        files = _extract_code_files(raw_response)
        return {"type": "code", "files": files, "raw": raw_response}
    else:  # md
        return {"type": "md", "content": raw_response.strip(), "raw": raw_response}


def _format_prior_artifact_for_context(phase_run_dict: dict) -> str:
    """Render a prior phase's artifact as context for downstream phases."""
    phase_name = phase_run_dict.get("phase_name", "?")
    role = phase_run_dict.get("agent_role", "?")
    artifact = phase_run_dict.get("output_artifact") or {}
    atype = artifact.get("type")

    header = f"## Prior Phase: {phase_name} ({role})"
    if atype == "json":
        data = artifact.get("data")
        if data:
            return f"{header}\n```json\n{json.dumps(data, indent=2)}\n```"
        return f"{header}\n(no structured output — raw text below)\n{artifact.get('raw', '')[:2000]}"
    elif atype == "code":
        files = artifact.get("files", []) or []
        if not files:
            return f"{header}\n(no files generated)"
        file_list = "\n".join(f"- {f['path']}" for f in files)
        previews = "\n\n".join(
            f"### {f['path']}\n```\n{f['content'][:1500]}\n```"
            for f in files[:5]
        )
        return f"{header}\nFiles written:\n{file_list}\n\n{previews}"
    else:  # md
        return f"{header}\n{artifact.get('content', '')[:3000]}"


# ─── Phase runner (one phase = one LLM call) ──────────────────────────────────
async def _run_phase(pipeline_id: str, phase_index: int):
    """Execute a single phase. Persists PhaseRun + artifact. Streams events."""
    from app.models.pipeline import Pipeline, PhaseRun
    from app.services.model_client import ModelClient
    from app.services.identity_context import build_identity_context
    from app.routes.workbench import _resolve_model

    # Load pipeline
    async with AsyncSessionLocal() as db:
        p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
        if not p:
            logger.error(f"_run_phase: pipeline {pipeline_id} not found")
            return
        phases = p.phases or []
        initial_task = p.initial_task
        auto_approve = p.auto_approve

        # Load all prior phase runs for context
        prior_runs = (await db.execute(
            select(PhaseRun)
            .where(PhaseRun.pipeline_id == pipeline_id)
            .where(PhaseRun.status.in_(("approved", "skipped")))
            .order_by(PhaseRun.phase_index)
        )).scalars().all()
        prior_run_dicts = [r.to_dict() for r in prior_runs]

    if phase_index >= len(phases):
        logger.info(f"Pipeline {pipeline_id}: all phases complete")
        await _db_update_pipeline(pipeline_id, status="completed", completed_at=datetime.utcnow())
        _push(pipeline_id, "pipeline_done", message="All phases complete.", status="completed")
        return

    phase_def = phases[phase_index]
    phase_name = phase_def["name"]
    agent_role = phase_def["role"]
    model_id = phase_def.get("model") or phase_def.get("default_model") or "claude-sonnet-4-6"

    # Create PhaseRun row
    phase_run_id = str(uuid.uuid4())
    started = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        pr = PhaseRun(
            id=phase_run_id,
            pipeline_id=pipeline_id,
            phase_index=phase_index,
            phase_name=phase_name,
            agent_role=agent_role,
            model_id=model_id,
            status="running",
            started_at=started,
            input_context={"prior_phases": [r["phase_name"] for r in prior_run_dicts]},
        )
        db.add(pr)
        await db.commit()

    await _db_update_pipeline(pipeline_id, status="running", current_phase_index=phase_index)
    _push(
        pipeline_id, "phase_started",
        phase_index=phase_index,
        phase_name=phase_name,
        agent_role=agent_role,
        phase_run_id=phase_run_id,
        model_id=model_id,
    )

    # Resolve model
    model_orm, provider_orm = await _resolve_model(model_id)
    if not model_orm:
        msg = (f"Could not resolve model '{model_id}' for phase {phase_name}. "
               f"The model may not exist, or its provider has no API key configured. "
               f"Check backend logs for details, or pick a different model for this phase.")
        logger.error(msg)
        await _db_update_phase(phase_run_id, status="failed", completed_at=datetime.utcnow())
        await _db_update_pipeline(pipeline_id, status="failed", completed_at=datetime.utcnow())
        _push(pipeline_id, "phase_failed", phase_index=phase_index, error=msg)
        _push(pipeline_id, "pipeline_done", message="Pipeline failed.", status="failed")
        return

    # Build messages: identity + phase system prompt + initial task + prior artifacts
    identity_block = build_identity_context(include_method=False)
    phase_prompt = phase_def.get("system_prompt", "")

    system_parts = []
    if identity_block:
        system_parts.append(identity_block)
    system_parts.append(f"# Your role: {agent_role}\n\n{phase_prompt}")
    system_prompt = "\n\n---\n\n".join(system_parts)

    # Build user message: task + all prior phase artifacts
    user_parts = [f"# Original task\n{initial_task}"]
    for prd in prior_run_dicts:
        user_parts.append(_format_prior_artifact_for_context(prd))
    user_parts.append(f"# Your turn: {phase_name}\nProduce your artifact per the instructions in your system prompt.")
    user_message = "\n\n---\n\n".join(user_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Run LLM
    client = ModelClient()
    full_response = ""
    input_tokens = 0
    output_tokens = 0
    llm_success = True
    llm_error = None

    _push(pipeline_id, "phase_thinking", phase_index=phase_index,
          message=f"{agent_role} is working with {model_orm.display_name or model_orm.model_id}…")

    try:
        stream = await client.call_model(
            model=model_orm,
            provider=provider_orm,
            messages=messages,
            stream=True,
            temperature=0.3,
            max_tokens=8000,
        )

        chunk_count = 0
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
                    input_tokens = (getattr(usage, "prompt_tokens", 0)
                                    or (usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0))
                    output_tokens = (getattr(usage, "completion_tokens", 0)
                                     or (usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0))
            except Exception:
                pass

            if delta:
                full_response += delta
                chunk_count += 1
                if chunk_count % 25 == 0:
                    _push(pipeline_id, "phase_progress",
                          phase_index=phase_index,
                          chars=len(full_response))

    except Exception as e:
        logger.error(f"LLM call failed in phase {phase_name} of pipeline {pipeline_id}: {e}")
        llm_success = False
        llm_error = str(e)

    # Estimate tokens if missing
    if input_tokens == 0:
        input_tokens = client.estimate_tokens(messages, model_orm)
    if output_tokens == 0 and full_response:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            output_tokens = len(enc.encode(full_response))
        except Exception:
            output_tokens = len(full_response) // 4

    # Write request_log for stats
    try:
        from app.models.request_log import RequestLog
        estimated_cost = client.estimate_cost(input_tokens, output_tokens, model_orm)
        async with AsyncSessionLocal() as db:
            log = RequestLog(
                model_id=str(model_orm.id),
                provider_id=str(provider_orm.id),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=int((datetime.utcnow() - started).total_seconds() * 1000),
                estimated_cost=estimated_cost,
                success=llm_success,
                error_message=llm_error,
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        logger.warning(f"request_log write failed: {e}")

    if not llm_success:
        await _db_update_phase(
            phase_run_id,
            status="failed",
            raw_response=full_response,
            completed_at=datetime.utcnow(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        await _db_update_pipeline(pipeline_id, status="failed", completed_at=datetime.utcnow())
        _push(pipeline_id, "phase_failed", phase_index=phase_index, error=llm_error)
        _push(pipeline_id, "pipeline_done", message="Pipeline failed.", status="failed")
        return

    # Extract structured artifact
    artifact = _build_artifact(phase_def, full_response)

    # If this is a "code" phase and we have a project_path, write files to disk
    if artifact.get("type") == "code" and artifact.get("files"):
        try:
            from app.models.workbench import WorkbenchSession
            async with AsyncSessionLocal() as db:
                sess = (await db.execute(
                    select(WorkbenchSession).where(WorkbenchSession.pipeline_id == pipeline_id)
                )).scalar_one_or_none()
                if sess and sess.project_path:
                    project_path = Path(sess.project_path)
                    written = []
                    for f in artifact["files"]:
                        rel = f["path"].lstrip("/\\")
                        abs_path = project_path / rel
                        try:
                            abs_path.parent.mkdir(parents=True, exist_ok=True)
                            abs_path.write_text(f["content"], encoding="utf-8")
                            written.append(rel)
                        except Exception as e:
                            logger.warning(f"Failed to write {rel}: {e}")
                    artifact["files_written_to_disk"] = written
                    _push(pipeline_id, "files_written", phase_index=phase_index, files=written)
        except Exception as e:
            logger.warning(f"File writing for phase failed: {e}")

    # Persist phase run (awaiting_approval or approved-if-auto)
    final_status = "approved" if auto_approve else "awaiting_approval"
    await _db_update_phase(
        phase_run_id,
        status=final_status,
        raw_response=full_response,
        output_artifact=artifact,
        completed_at=datetime.utcnow(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    _push(
        pipeline_id, "phase_completed",
        phase_index=phase_index,
        phase_name=phase_name,
        agent_role=agent_role,
        phase_run_id=phase_run_id,
        artifact=artifact,
        status=final_status,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    if auto_approve:
        # Advance immediately
        await _advance_to_next(pipeline_id, phase_index)
    else:
        await _db_update_pipeline(pipeline_id, status="awaiting_approval")
        _push(pipeline_id, "awaiting_approval", phase_index=phase_index,
              message=f"Phase '{phase_name}' complete — awaiting your approval.")


async def _advance_to_next(pipeline_id: str, current_index: int):
    """Move to the next phase. If at end, complete the pipeline."""
    from app.models.pipeline import Pipeline
    async with AsyncSessionLocal() as db:
        p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
        if not p:
            return
        total = len(p.phases or [])
    next_index = current_index + 1
    if next_index >= total:
        await _db_update_pipeline(pipeline_id, status="completed", completed_at=datetime.utcnow(),
                                  current_phase_index=current_index)
        _push(pipeline_id, "pipeline_done", message="All phases complete.", status="completed")
        return
    await _db_update_pipeline(pipeline_id, current_phase_index=next_index, status="running")
    asyncio.create_task(_run_phase(pipeline_id, next_index))


# ─── Routes ───────────────────────────────────────────────────────────────────
@router.get("/methods/{method_id}/phases", dependencies=[Depends(verify_api_key)])
async def preview_phases(method_id: str):
    """Return the ordered list of phases for a method (without starting a pipeline)."""
    from app.services.phase_templates import get_phases_for_method, list_supported_methods
    try:
        phases = get_phases_for_method(method_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Method '{method_id}' not supported. Available: {list_supported_methods()}"
        )
    # Strip the full system_prompt for preview (too long); keep a short hint
    return {
        "method_id": method_id,
        "phases": [
            {
                "name": p["name"],
                "role": p["role"],
                "default_model": p["default_model"],
                "artifact_type": p["artifact_type"],
            }
            for p in phases
        ],
    }


@router.post("", dependencies=[Depends(verify_api_key)])
async def create_pipeline(body: PipelineCreate, db: AsyncSession = Depends(get_db)):
    """Create and start a multi-agent pipeline attached to a workbench session."""
    from app.models.pipeline import Pipeline
    from app.models.workbench import WorkbenchSession
    from app.services.phase_templates import get_phases_for_method, list_supported_methods

    # Validate method
    try:
        template_phases = get_phases_for_method(body.method_id)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Method '{body.method_id}' does not support pipelines. "
                   f"Supported: {list_supported_methods()}"
        )

    # Validate session
    session = (await db.execute(
        select(WorkbenchSession).where(WorkbenchSession.id == body.session_id)
    )).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail=f"Workbench session {body.session_id} not found")

    # Apply per-phase model overrides if provided
    overrides = body.model_overrides or {}
    for phase in template_phases:
        if phase["name"] in overrides:
            phase["model"] = overrides[phase["name"]]
        else:
            phase["model"] = phase.get("default_model")

    # Create Pipeline row
    pipeline_id = str(uuid.uuid4())
    pipeline = Pipeline(
        id=pipeline_id,
        session_id=body.session_id,
        method_id=body.method_id,
        phases=template_phases,
        current_phase_index=0,
        status="pending",
        auto_approve=body.auto_approve,
        initial_task=body.task,
    )
    db.add(pipeline)

    # Link session -> pipeline
    session.pipeline_id = pipeline_id
    await db.commit()

    # Set up SSE queue
    _queues[pipeline_id] = asyncio.Queue(maxsize=1000)
    _event_logs[pipeline_id] = []

    _push(pipeline_id, "pipeline_created",
          method_id=body.method_id,
          phases=[{"name": p["name"], "role": p["role"], "model": p.get("model")} for p in template_phases],
          auto_approve=body.auto_approve)

    # Kick off phase 0
    asyncio.create_task(_run_phase(pipeline_id, 0))

    return pipeline.to_dict()


@router.get("", dependencies=[Depends(verify_api_key)])
async def list_pipelines(db: AsyncSession = Depends(get_db)):
    from app.models.pipeline import Pipeline
    result = await db.execute(
        select(Pipeline).order_by(desc(Pipeline.created_at)).limit(100)
    )
    pipelines = result.scalars().all()
    return {"data": [p.to_dict() for p in pipelines], "total": len(pipelines)}


@router.get("/{pipeline_id}", dependencies=[Depends(verify_api_key)])
async def get_pipeline(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.pipeline import Pipeline, PhaseRun
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    runs = (await db.execute(
        select(PhaseRun).where(PhaseRun.pipeline_id == pipeline_id).order_by(PhaseRun.phase_index, PhaseRun.created_at)
    )).scalars().all()

    return {
        **p.to_dict(),
        "phase_runs": [r.to_dict() for r in runs],
    }


@router.post("/{pipeline_id}/approve", dependencies=[Depends(verify_api_key)])
async def approve_phase(pipeline_id: str, body: PipelineApprove, db: AsyncSession = Depends(get_db)):
    """Approve the current phase and advance to the next."""
    from app.models.pipeline import Pipeline, PhaseRun
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if p.status != "awaiting_approval":
        raise HTTPException(status_code=409,
                            detail=f"Pipeline is not awaiting approval (status={p.status})")

    # Find the awaiting_approval run at current index
    pr = (await db.execute(
        select(PhaseRun)
        .where(PhaseRun.pipeline_id == pipeline_id)
        .where(PhaseRun.phase_index == p.current_phase_index)
        .where(PhaseRun.status == "awaiting_approval")
        .order_by(desc(PhaseRun.created_at))
        .limit(1)
    )).scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="No phase awaiting approval")

    pr.status = "approved"
    if body.feedback:
        pr.user_feedback = body.feedback
    await db.commit()

    _push(pipeline_id, "phase_approved", phase_index=p.current_phase_index, feedback=body.feedback)

    # Advance to next phase
    await _advance_to_next(pipeline_id, p.current_phase_index)

    return {"ok": True, "advanced_to": p.current_phase_index + 1}


@router.post("/{pipeline_id}/reject", dependencies=[Depends(verify_api_key)])
async def reject_phase(pipeline_id: str, body: PipelineReject, db: AsyncSession = Depends(get_db)):
    """Reject the current phase with feedback — re-runs the same phase."""
    from app.models.pipeline import Pipeline, PhaseRun
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if p.status != "awaiting_approval":
        raise HTTPException(status_code=409,
                            detail=f"Pipeline is not awaiting approval (status={p.status})")

    pr = (await db.execute(
        select(PhaseRun)
        .where(PhaseRun.pipeline_id == pipeline_id)
        .where(PhaseRun.phase_index == p.current_phase_index)
        .where(PhaseRun.status == "awaiting_approval")
        .order_by(desc(PhaseRun.created_at))
        .limit(1)
    )).scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="No phase awaiting approval")

    pr.status = "rejected"
    pr.user_feedback = body.feedback
    await db.commit()

    _push(pipeline_id, "phase_rejected", phase_index=p.current_phase_index, feedback=body.feedback)

    # Bake the rejection feedback into the phase's system prompt for the re-run
    # We do this by mutating the pipeline.phases entry for this index in-place.
    try:
        phases = list(p.phases or [])
        if 0 <= p.current_phase_index < len(phases):
            original = phases[p.current_phase_index].get("system_prompt", "")
            feedback_block = (f"\n\n# User rejected your previous attempt — feedback:\n"
                              f"{body.feedback}\n\nAddress this feedback in your next attempt.")
            if feedback_block not in original:
                phases[p.current_phase_index]["system_prompt"] = original + feedback_block
            await _db_update_pipeline(pipeline_id, phases=phases, status="running")
    except Exception as e:
        logger.warning(f"Could not inject rejection feedback: {e}")

    # Re-run the same phase
    asyncio.create_task(_run_phase(pipeline_id, p.current_phase_index))

    return {"ok": True, "re_running_phase": p.current_phase_index}


@router.post("/{pipeline_id}/skip", dependencies=[Depends(verify_api_key)])
async def skip_phase(pipeline_id: str, body: PipelineSkip, db: AsyncSession = Depends(get_db)):
    """Skip the current phase and advance."""
    from app.models.pipeline import Pipeline, PhaseRun
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if p.status not in ("awaiting_approval", "running"):
        raise HTTPException(status_code=409,
                            detail=f"Pipeline cannot skip from status={p.status}")

    # Mark current phase run (if any) as skipped
    pr = (await db.execute(
        select(PhaseRun)
        .where(PhaseRun.pipeline_id == pipeline_id)
        .where(PhaseRun.phase_index == p.current_phase_index)
        .order_by(desc(PhaseRun.created_at))
        .limit(1)
    )).scalar_one_or_none()
    if pr:
        pr.status = "skipped"
        if body.reason:
            pr.user_feedback = body.reason
        await db.commit()

    _push(pipeline_id, "phase_skipped", phase_index=p.current_phase_index, reason=body.reason)

    await _advance_to_next(pipeline_id, p.current_phase_index)
    return {"ok": True, "skipped_phase": p.current_phase_index}


@router.post("/{pipeline_id}/retry", dependencies=[Depends(verify_api_key)])
async def retry_phase(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    """Retry a failed phase (or the current phase if pipeline failed mid-run)."""
    from app.models.pipeline import Pipeline
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if p.status not in ("failed", "cancelled"):
        raise HTTPException(status_code=409,
                            detail=f"Can only retry from failed/cancelled (status={p.status})")

    # Reset pipeline status and re-run current phase
    await _db_update_pipeline(pipeline_id, status="running", completed_at=None)
    _push(pipeline_id, "pipeline_retry", phase_index=p.current_phase_index,
          message=f"Retrying phase {p.current_phase_index}")

    asyncio.create_task(_run_phase(pipeline_id, p.current_phase_index))
    return {"ok": True, "retrying_phase": p.current_phase_index}


@router.post("/{pipeline_id}/cancel", dependencies=[Depends(verify_api_key)])
async def cancel_pipeline(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.pipeline import Pipeline
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    await _db_update_pipeline(pipeline_id, status="cancelled", completed_at=datetime.utcnow())
    _push(pipeline_id, "pipeline_done", message="Pipeline cancelled.", status="cancelled")
    return {"ok": True}


@router.get("/{pipeline_id}/stream")
async def stream_pipeline(pipeline_id: str, request: Request):
    """SSE stream — no auth (EventSource limitation)."""
    from app.models.pipeline import Pipeline, PhaseRun
    async with AsyncSessionLocal() as db:
        p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
        if not p:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        runs = (await db.execute(
            select(PhaseRun).where(PhaseRun.pipeline_id == pipeline_id).order_by(PhaseRun.phase_index, PhaseRun.created_at)
        )).scalars().all()
        init_payload = {**p.to_dict(), "phase_runs": [r.to_dict() for r in runs]}

    async def event_generator() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type':'init','payload':init_payload})}\n\n"

        queue = _queues.get(pipeline_id)
        if not queue:
            # Pipeline exists but no live queue — replay stored events
            for evt in _event_logs.get(pipeline_id, []):
                yield f"data: {json.dumps(evt)}\n\n"
                await asyncio.sleep(0.02)
            # Final synthetic done if terminal
            if p.status in ("completed", "failed", "cancelled"):
                yield f"data: {json.dumps({'type':'pipeline_done','payload':{'status':p.status}})}\n\n"
            return

        while True:
            if await request.is_disconnected():
                break
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(evt)}\n\n"
                if evt.get("type") == "pipeline_done":
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type':'ping','payload':{}})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
    )
