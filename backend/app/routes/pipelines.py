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

        # Load phase runs from dependency phases only (not all prior phases).
        # This ensures each phase gets context specifically from the phases
        # it declared in depends_on, enabling correct parallel execution.
        all_prior_runs = (await db.execute(
            select(PhaseRun)
            .where(PhaseRun.pipeline_id == pipeline_id)
            .where(PhaseRun.status.in_(("approved", "skipped", "completed")))
            .order_by(PhaseRun.phase_index)
        )).scalars().all()

    if phase_index >= len(phases):
        logger.info(f"Pipeline {pipeline_id}: all phases complete")
        await _db_update_pipeline(pipeline_id, status="completed", completed_at=datetime.utcnow())
        _push(pipeline_id, "pipeline_done", message="All phases complete.", status="completed")
        return

    phase_def = phases[phase_index]
    phase_name = phase_def["name"]

    # ── Handle branch phases — no LLM call, just routing ───────────────────
    if phase_def.get("phase_type") == "branch":
        from app.services.phase_templates import evaluate_branch

        # Get parent output from the most recent prior run
        parent_output = ""
        if prior_run_dicts:
            last = prior_run_dicts[-1]
            artifact = last.get("output_artifact") or {}
            if artifact.get("type") == "json" and artifact.get("data") is not None:
                parent_output = json.dumps(artifact["data"])
            elif artifact.get("raw"):
                parent_output = artifact["raw"]

        target = evaluate_branch(phase_def, parent_output)

        # Create PhaseRun as instantly completed (no LLM, no tokens)
        run_id = str(uuid.uuid4())
        now = datetime.utcnow()
        async with AsyncSessionLocal() as db:
            pr = PhaseRun(
                id=run_id,
                pipeline_id=pipeline_id,
                phase_index=phase_index,
                phase_name=phase_name,
                agent_role="branch",
                model_id=None,
                status="approved",
                started_at=now,
                completed_at=now,
                input_context={
                    "branch_target": target,
                    "parent_output_preview": (parent_output or "")[:200],
                },
                output_artifact={"type": "branch", "target": target},
            )
            db.add(pr)
            await db.commit()

        _push(pipeline_id, "phase_branch",
              phase_index=phase_index,
              phase_name=phase_name,
              target=target)

        logger.info(f"Pipeline {pipeline_id}: branch phase '{phase_name}' routed to '{target}'")

        await _advance_to_next(pipeline_id, phase_index)
        return

    agent_role = phase_def["role"]

    # Filter prior runs to only those from declared dependencies
    depends_on = set(phase_def.get("depends_on") or [])
    if depends_on:
        prior_run_dicts = [
            r.to_dict() for r in all_prior_runs
            if r.phase_name in depends_on
        ]
    else:
        # No explicit deps — for phases with empty depends_on (root phases),
        # no prior context is injected.  For legacy phases without the field,
        # fall back to all prior runs so existing behaviour is preserved.
        if "depends_on" in phase_def:
            prior_run_dicts = []
        else:
            prior_run_dicts = [r.to_dict() for r in all_prior_runs]

    # ── Condition evaluation ─────────────────────────────────────────────
    if phase_def.get("conditions"):
        from app.services.phase_templates import evaluate_phase_conditions, format_condition_reason

        parent_output: Optional[str] = None
        if prior_run_dicts:
            last_parent = prior_run_dicts[-1]
            artifact_data = last_parent.get("output_artifact") or {}
            if artifact_data.get("type") == "json" and artifact_data.get("data") is not None:
                parent_output = json.dumps(artifact_data["data"])
            elif artifact_data.get("raw"):
                parent_output = artifact_data["raw"]

        if not evaluate_phase_conditions(phase_def, parent_output):
            skip_reasons = [format_condition_reason(c) for c in phase_def["conditions"]]
            reason = "; ".join(skip_reasons)

            skip_run_id = str(uuid.uuid4())
            async with AsyncSessionLocal() as db:
                pr = PhaseRun(
                    id=skip_run_id,
                    pipeline_id=pipeline_id,
                    phase_index=phase_index,
                    phase_name=phase_name,
                    agent_role=agent_role,
                    model_id=None,
                    status="skipped",
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    input_context={"skip_reason": reason},
                )
                db.add(pr)
                await db.commit()

            logger.info("Pipeline %s: skipping phase %d (%s) — %s", pipeline_id, phase_index, phase_name, reason)
            _push(pipeline_id, "phase_skipped", phase_index=phase_index, phase_name=phase_name, reason=reason)
            await _advance_to_next(pipeline_id)
            return

    # Model resolution chain (highest priority wins):
    #   1. Per-phase user override (phase_def["model"] from model_overrides)
    #   2. Agent bound to this method_phase → its persona → persona.primary_model
    #   3. Agent bound to this method_phase → its own model_id (if no persona)
    #   4. Persona matching phase name (legacy, direct persona match)
    #   5. Template default_model (fallback)
    resolved_model = None
    resolved_system_prompt = None  # persona + agent prompts prepended to phase prompt
    resolved_via = None             # for logging

    if not phase_def.get("model"):
        try:
            from app.models.agent import Agent
            from app.models.persona import Persona
            from app.models.model import Model as ModelORM
            from sqlalchemy import func as sqlfunc

            async with AsyncSessionLocal() as db:
                # Look up the agent bound to this phase (case-insensitive)
                agent = (await db.execute(
                    select(Agent)
                    .where(sqlfunc.lower(Agent.method_phase) == phase_name.lower())
                    .where(Agent.is_active == True)
                    .order_by(Agent.created_at)
                    .limit(1)
                )).scalar_one_or_none()

                if agent:
                    extra_prompts = []
                    # If the agent has its own system_prompt, prepend it
                    if agent.system_prompt:
                        extra_prompts.append(f"# Agent: {agent.name}\n{agent.system_prompt}")
                    # Resolve model via persona if attached
                    if agent.persona_id:
                        persona = (await db.execute(
                            select(Persona).where(Persona.id == agent.persona_id)
                        )).scalar_one_or_none()
                        if persona:
                            if persona.system_prompt:
                                extra_prompts.append(f"# Persona: {persona.name}\n{persona.system_prompt}")
                            if persona.primary_model_id:
                                m = (await db.execute(select(ModelORM).where(ModelORM.id == persona.primary_model_id))).scalar_one_or_none()
                                if m:
                                    resolved_model = m.model_id
                                    resolved_via = f"agent '{agent.name}' → persona '{persona.name}'"
                    # Fallback: agent's own model_id if no persona
                    if not resolved_model and agent.model_id:
                        m = (await db.execute(select(ModelORM).where(ModelORM.id == agent.model_id))).scalar_one_or_none()
                        if m:
                            resolved_model = m.model_id
                            resolved_via = f"agent '{agent.name}' (direct model)"
                    if extra_prompts:
                        resolved_system_prompt = "\n\n".join(extra_prompts)

                # Legacy fallback: persona with a matching name, even if no agent
                if not resolved_model:
                    persona = (await db.execute(
                        select(Persona).where(sqlfunc.lower(Persona.name) == phase_name.lower())
                    )).scalar_one_or_none()
                    if persona and persona.primary_model_id:
                        m = (await db.execute(select(ModelORM).where(ModelORM.id == persona.primary_model_id))).scalar_one_or_none()
                        if m:
                            resolved_model = m.model_id
                            resolved_via = f"persona '{persona.name}' (name match, no agent)"
                            if persona.system_prompt:
                                resolved_system_prompt = f"# Persona: {persona.name}\n{persona.system_prompt}"
        except Exception as e:
            logger.warning(f"Phase '{phase_name}' resolution lookup failed: {e}")

    if resolved_via:
        logger.info(f"Phase '{phase_name}' → {resolved_via} → model '{resolved_model}'")

    model_id = phase_def.get("model") or resolved_model or phase_def.get("default_model") or "claude-sonnet-4-6"
    persona_system_prompt = resolved_system_prompt  # used below when composing the phase system prompt

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
            input_context={
                "prior_phases": [r["phase_name"] for r in prior_run_dicts],
                "depends_on": list(depends_on),
            },
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
        _push(pipeline_id, "phase_failed", phase_index=phase_index, error=msg)
        # Don't kill the entire pipeline — let _advance_to_next decide if
        # other branches can continue or if the pipeline is fully blocked.
        await _advance_to_next(pipeline_id)
        return

    # Build messages: identity + persona prompt + phase system prompt + initial task + prior artifacts
    identity_block = build_identity_context(include_method=False)
    phase_prompt = phase_def.get("system_prompt", "")

    system_parts = []
    if identity_block:
        system_parts.append(identity_block)
    if persona_system_prompt:
        # User-defined persona voice/instructions take effect before the phase-specific role
        system_parts.append(f"# Persona\n{persona_system_prompt}")
    system_parts.append(f"# Your role: {agent_role}\n\n{phase_prompt}")
    system_prompt = "\n\n---\n\n".join(system_parts)

    # Load the session's project path so we can inject the current file snapshot.
    # Without this, code phases hallucinate new files instead of editing existing ones.
    session_project_path: Optional[Path] = None
    try:
        from app.models.workbench import WorkbenchSession
        async with AsyncSessionLocal() as db:
            sess = (await db.execute(
                select(WorkbenchSession).where(WorkbenchSession.pipeline_id == pipeline_id)
            )).scalar_one_or_none()
            if sess and sess.project_path:
                session_project_path = Path(sess.project_path)
    except Exception as e:
        logger.debug(f"Could not resolve session project_path: {e}")

    project_snapshot = ""
    if session_project_path and session_project_path.exists():
        try:
            from app.routes.workbench import _read_project_snapshot
            project_snapshot = _read_project_snapshot(session_project_path)
        except Exception as e:
            logger.debug(f"Snapshot read failed: {e}")

    # Build user message: task + project snapshot + all prior phase artifacts
    user_parts = [f"# Original task\n{initial_task}"]
    if project_snapshot:
        user_parts.append(project_snapshot)
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
            max_tokens=16000,
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
        err_str = str(e)
        logger.error(f"LLM call failed in phase {phase_name} of pipeline {pipeline_id}: {e}")
        # Enrich common provider errors with a user-facing message
        friendly = err_str
        low = err_str.lower()
        if "insufficient_quota" in low or "exceeded your current quota" in low:
            friendly = (f"OpenAI quota exceeded — your account is out of credits. "
                        f"Top up at https://platform.openai.com/account/billing, or pick a different provider for this phase.")
        elif "authenticationerror" in low or "x-api-key" in low or "401" in err_str or "invalid_api_key" in low:
            friendly = f"Provider rejected the API key for model '{model_id}'. Check the key in your .env file."
        elif "ratelimiterror" in low or "429" in err_str:
            friendly = f"Rate-limited by provider for model '{model_id}'. Wait and retry, or switch models."
        elif "notfounderror" in low or "model_not_found" in low or "does not exist" in low or ("404" in err_str and "openai" in low):
            friendly = (f"Model '{model_id}' doesn't exist on the provider's API. "
                        f"It may have been renamed or removed. Pick a different model for this phase.")
        elif "timeout" in low or "timed out" in low:
            friendly = f"Provider call for model '{model_id}' timed out."
        llm_success = False
        llm_error = friendly

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
        _push(pipeline_id, "phase_failed", phase_index=phase_index, error=llm_error)
        # Let _advance_to_next decide pipeline-level status — other parallel
        # branches may still be running or runnable.
        await _advance_to_next(pipeline_id)
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
                    project_path_for_write = Path(sess.project_path)
                    written = []
                    for f in artifact["files"]:
                        rel = f["path"].lstrip("/\\")
                        abs_path = project_path_for_write / rel
                        try:
                            abs_path.parent.mkdir(parents=True, exist_ok=True)
                            abs_path.write_text(f["content"], encoding="utf-8")
                            written.append(rel)
                        except Exception as e:
                            logger.warning(f"Failed to write {rel}: {e}")
                    artifact["files_written_to_disk"] = written
                    _push(pipeline_id, "files_written", phase_index=phase_index, files=written)
                elif sess and not sess.project_path:
                    # Warn the user — without a project path, code phases produce
                    # artifacts but nothing lands on disk.
                    logger.warning(f"Pipeline {pipeline_id} code phase has no project_path — files NOT saved")
                    _push(pipeline_id, "warning",
                          phase_index=phase_index,
                          message=f"Code phase '{phase_name}' produced {len(artifact['files'])} files but session has no project_path — files won't be saved to disk. Attach a project when creating the session.")
        except Exception as e:
            logger.warning(f"File writing for phase failed: {e}")

    # Execute any CMD: blocks the agent emitted (same 3-tier classifier as workbench)
    cmd_results_for_context: list[str] = []
    try:
        from app.services.command_executor import (
            parse_cmd_blocks, create_command_record, execute_and_record,
            classify_with_project_trust, format_command_for_context,
            get_first_github_token,
        )
        from app.services.command_classifier import CommandTier
        gh_token = get_first_github_token()

        cmds = parse_cmd_blocks(full_response)
        if cmds and session_project_path:
            # Load session bypass + project sandbox mode
            bypass_mode = False
            sandbox_mode = "full"
            proj_path_str = str(session_project_path)
            sess_row = None
            try:
                from app.models.workbench import WorkbenchSession
                async with AsyncSessionLocal() as db:
                    sess_row = (await db.execute(
                        select(WorkbenchSession).where(WorkbenchSession.pipeline_id == pipeline_id)
                    )).scalar_one_or_none()
                    if sess_row:
                        bypass_mode = bool(sess_row.bypass_approvals)
                        proj_id = sess_row.project_id
                        if proj_id:
                            try:
                                import json as _json
                                from pathlib import Path as _P
                                data_dir = _P(__file__).parent.parent.parent.parent / "data"
                                pf = data_dir / "projects.json"
                                if pf.exists():
                                    projects = _json.loads(pf.read_text(encoding="utf-8"))
                                    proj = projects.get(str(proj_id)) or {}
                                    sandbox_mode = proj.get("sandbox_mode") or "full"
                            except Exception:
                                pass
            except Exception:
                pass

            session_id_for_cmds = sess_row.id if sess_row else None
            if session_id_for_cmds:
                _push(pipeline_id, "info", phase_index=phase_index,
                      message=f"Phase emitted {len(cmds)} command(s) to execute")
                for raw_cmd in cmds:
                    tier = classify_with_project_trust(raw_cmd, sandbox_mode, proj_path_str)
                    if tier == CommandTier.BLOCKED:
                        continue
                    # In pipelines we respect the same tiering BUT we can't
                    # pause for approval mid-phase easily. Policy: auto-approve
                    # auto+notice tiers, skip approval tier (record it so user
                    # can approve via workbench UI if they click through).
                    if tier == CommandTier.APPROVAL and not bypass_mode:
                        # Record as pending so it shows up in the workbench log
                        rec_id = await create_command_record(
                            session_id_for_cmds, raw_cmd, tier,
                            pipeline_id=pipeline_id, phase_run_id=phase_run_id,
                            initial_status="pending",
                        )
                        _push(pipeline_id, "command_awaiting_approval",
                              command_id=rec_id, command=raw_cmd, tier=tier.value,
                              phase_index=phase_index)
                        continue
                    # Run inline (auto, notice, or bypass)
                    rec_id = await create_command_record(
                        session_id_for_cmds, raw_cmd, tier,
                        pipeline_id=pipeline_id, phase_run_id=phase_run_id,
                        initial_status="running",
                    )
                    _push(pipeline_id, "command_running",
                          command_id=rec_id, command=raw_cmd, tier=tier.value,
                          phase_index=phase_index)
                    result = await execute_and_record(
                        rec_id, raw_cmd, session_project_path, bypass_used=bypass_mode, github_token=gh_token
                    )
                    _push(pipeline_id, "command_completed", phase_index=phase_index, **result)
                    cmd_results_for_context.append(format_command_for_context(result))

        elif cmds and not session_project_path:
            logger.warning(f"Pipeline {pipeline_id} phase emitted {len(cmds)} CMD: blocks but no project_path — commands skipped")
            _push(pipeline_id, "warning", phase_index=phase_index,
                  message=f"Phase emitted {len(cmds)} commands but session has no project — commands skipped")
    except Exception as e:
        logger.warning(f"Command execution in phase failed: {e}")

    # Append command results to the artifact for downstream phases to see
    if cmd_results_for_context:
        existing_raw = artifact.get("raw", "")
        artifact["raw"] = existing_raw + "\n\n## Commands executed:\n" + "\n\n".join(cmd_results_for_context)

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
        # Advance immediately — launch any phases whose deps are now met
        await _advance_to_next(pipeline_id)
    else:
        await _db_update_pipeline(pipeline_id, status="awaiting_approval")
        _push(pipeline_id, "awaiting_approval", phase_index=phase_index,
              message=f"Phase '{phase_name}' complete — awaiting your approval.")


async def _advance_to_next(pipeline_id: str, _current_index: int = -1):
    """Advance pipeline by launching all phases whose dependencies are met.

    Uses the dependency graph (``depends_on`` on each phase) instead of a
    simple sequential index.  All phases whose deps are fully satisfied are
    launched concurrently via ``asyncio.create_task``.

    The ``_current_index`` parameter is accepted for backward-compat with
    existing call-sites but is **not used** for scheduling decisions.
    """
    from app.models.pipeline import Pipeline, PhaseRun
    from app.services.phase_templates import get_ready_phases

    async with AsyncSessionLocal() as db:
        p = (await db.execute(
            select(Pipeline).where(Pipeline.id == pipeline_id)
        )).scalar_one_or_none()
        if not p:
            return
        phases = p.phases or []
        if not phases:
            await _db_update_pipeline(
                pipeline_id, status="completed", completed_at=datetime.utcnow()
            )
            _push(pipeline_id, "pipeline_done",
                  message="No phases to run.", status="completed")
            return

        # Gather status of every PhaseRun for this pipeline
        phase_runs = (await db.execute(
            select(PhaseRun)
            .where(PhaseRun.pipeline_id == pipeline_id)
            .order_by(PhaseRun.phase_index)
        )).scalars().all()

    # Classify runs by status
    completed_names: set[str] = set()
    running_names: set[str] = set()
    failed_names: set[str] = set()
    for run in phase_runs:
        if run.status in ("completed", "skipped", "approved"):
            completed_names.add(run.phase_name)
        elif run.status in ("running", "awaiting_approval"):
            running_names.add(run.phase_name)
        elif run.status == "failed":
            failed_names.add(run.phase_name)

    # Determine which phases are ready to launch
    ready = get_ready_phases(phases, completed_names)
    # Filter out phases that are already running or completed
    ready = [ph for ph in ready
             if ph["name"] not in running_names
             and ph["name"] not in completed_names]

    all_phase_names = {ph["name"] for ph in phases}

    if not ready and not running_names:
        # Nothing running and nothing to launch — pipeline is done (or stuck
        # because of failures blocking downstream).
        if completed_names | failed_names >= all_phase_names:
            # Every phase has a terminal status
            final_status = "completed" if not failed_names else "failed"
            # Update current_phase_index to the highest completed index for display
            max_idx = max(
                (i for i, ph in enumerate(phases) if ph["name"] in completed_names),
                default=len(phases) - 1,
            )
            await _db_update_pipeline(
                pipeline_id,
                status=final_status,
                completed_at=datetime.utcnow(),
                current_phase_index=max_idx,
            )
            if final_status == "completed":
                _push(pipeline_id, "pipeline_done",
                      message="All phases complete.", status="completed")
            else:
                _push(pipeline_id, "pipeline_done",
                      message="Pipeline finished with failures.", status="failed")
        else:
            # Some phases still pending but nothing can run — blocked by
            # failed dependencies.  Mark as failed so users can retry.
            await _db_update_pipeline(
                pipeline_id, status="failed", completed_at=datetime.utcnow()
            )
            _push(pipeline_id, "pipeline_done",
                  message="Pipeline blocked — upstream phase(s) failed.",
                  status="failed")
        return

    if not ready:
        # Phases are still running; nothing new to launch yet — just wait.
        return

    # Launch all ready phases concurrently
    # Update current_phase_index to the lowest ready index (for display)
    first_ready_idx = next(
        i for i, ph in enumerate(phases) if ph["name"] == ready[0]["name"]
    )
    await _db_update_pipeline(
        pipeline_id, current_phase_index=first_ready_idx, status="running"
    )

    for phase in ready:
        phase_index = next(
            i for i, ph in enumerate(phases) if ph["name"] == phase["name"]
        )
        asyncio.create_task(_run_phase(pipeline_id, phase_index))


# ─── Routes ───────────────────────────────────────────────────────────────────
@router.get("/methods/{method_id}/phases", dependencies=[Depends(verify_api_key)])
async def preview_phases(method_id: str):
    """Return the ordered list of phases for a method (without starting a pipeline).

    For each phase, reports the full Phase → Agent → Persona → Model chain
    so the frontend can show the user what will actually run.
    """
    from app.services.phase_templates import get_phases_for_method, list_supported_methods
    from app.models.agent import Agent
    from app.models.persona import Persona
    from app.models.model import Model as ModelORM
    try:
        phases = get_phases_for_method(method_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Method '{method_id}' not supported. Available: {list_supported_methods()}"
        )

    from sqlalchemy import func as sqlfunc
    async with AsyncSessionLocal() as db:
        # All active agents keyed by method_phase
        agent_rows = (await db.execute(
            select(Agent).where(Agent.is_active == True).where(Agent.method_phase.isnot(None))
        )).scalars().all()
        agent_by_phase = {}
        for a in agent_rows:
            key = (a.method_phase or "").lower()
            if key and key not in agent_by_phase:  # first wins (ordered by created_at already? no — keep consistent)
                agent_by_phase[key] = a

        persona_rows = (await db.execute(select(Persona))).scalars().all()
        persona_by_id = {str(p.id): p for p in persona_rows}
        persona_by_name = {p.name.lower(): p for p in persona_rows}

        model_rows = (await db.execute(select(ModelORM))).scalars().all()
        model_by_id = {str(m.id): m for m in model_rows}

    def chain_info(phase_name: str) -> dict:
        """Resolve the agent → persona → model chain for this phase."""
        result = {
            "has_agent": False, "agent_name": None,
            "has_persona": False, "persona_name": None,
            "resolved_model": None, "resolved_via": None,
        }
        # 1. Agent bound via method_phase
        agent = agent_by_phase.get(phase_name.lower())
        if agent:
            result["has_agent"] = True
            result["agent_name"] = agent.name
            # 1a. Agent -> Persona -> Model
            if agent.persona_id:
                persona = persona_by_id.get(str(agent.persona_id))
                if persona:
                    result["has_persona"] = True
                    result["persona_name"] = persona.name
                    if persona.primary_model_id:
                        m = model_by_id.get(str(persona.primary_model_id))
                        if m:
                            result["resolved_model"] = m.model_id
                            result["resolved_via"] = "agent→persona"
                            return result
            # 1b. Agent -> direct model
            if agent.model_id:
                m = model_by_id.get(str(agent.model_id))
                if m:
                    result["resolved_model"] = m.model_id
                    result["resolved_via"] = "agent→model"
                    return result
        # 2. Legacy fallback — persona matching the phase name directly
        persona = persona_by_name.get(phase_name.lower())
        if persona:
            result["has_persona"] = True
            result["persona_name"] = persona.name
            if persona.primary_model_id:
                m = model_by_id.get(str(persona.primary_model_id))
                if m:
                    result["resolved_model"] = m.model_id
                    result["resolved_via"] = "persona name-match"
                    return result
        # 3. Nothing resolved — frontend will show template default
        return result

    return {
        "method_id": method_id,
        "phases": [
            {
                "name": p["name"],
                "role": p["role"],
                "default_model": p["default_model"],
                "artifact_type": p["artifact_type"],
                "depends_on": p.get("depends_on", []),
                **chain_info(p["name"]),
                # Back-compat for existing frontend code
                "persona_model": None,  # replaced by resolved_model
            }
            for p in phases
        ],
    }


@router.post("", dependencies=[Depends(verify_api_key)])
async def create_pipeline(body: PipelineCreate, db: AsyncSession = Depends(get_db)):
    """Create and start a multi-agent pipeline attached to a workbench session."""
    from app.models.pipeline import Pipeline
    from app.models.workbench import WorkbenchSession
    from app.services.phase_templates import get_phases_for_method, list_supported_methods, validate_phase_dag

    # Resolve method — if "stack" or "active", use the currently-active method
    # stack from the Methods page. The primary (first) method in the stack
    # determines the phase structure; other stacked methods' prompts get
    # injected into every phase.
    from app.routes.methods import _load_state as _load_method_state, BUILT_IN_METHODS, _build_stack_prompt
    effective_method_id = body.method_id
    stacked_prompt = ""  # extra prompt from non-primary stacked methods

    if body.method_id in ("stack", "active"):
        method_state = _load_method_state()
        stack = method_state.get("active_stack", [])
        primary = stack[0] if stack else method_state.get("active_method", "standard")
        effective_method_id = primary
        # Build stacked prompt from non-primary methods
        non_primary = [m for m in stack if m != primary]
        if non_primary:
            stacked_prompt = _build_stack_prompt(non_primary)
            logger.info(f"Pipeline using stack: primary={primary}, also applying: {non_primary}")
    elif body.method_id in ("bmad", "gsd", "superpowers"):
        # Explicit single method — still check if there are stacked methods
        # that should layer on top
        method_state = _load_method_state()
        stack = method_state.get("active_stack", [])
        if len(stack) > 1 and body.method_id in stack:
            non_primary = [m for m in stack if m != body.method_id]
            if non_primary:
                stacked_prompt = _build_stack_prompt(non_primary)
                logger.info(f"Pipeline method={body.method_id}, layering stack: {non_primary}")

    # Validate method
    try:
        template_phases = get_phases_for_method(effective_method_id)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Method '{effective_method_id}' does not support pipelines. "
                   f"Supported: {list_supported_methods()}"
        )

    # Validate phase dependency DAG
    dag_errors = validate_phase_dag(template_phases)
    if dag_errors:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid phase dependency graph: {'; '.join(dag_errors)}"
        )

    # Validate session
    session = (await db.execute(
        select(WorkbenchSession).where(WorkbenchSession.id == body.session_id)
    )).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail=f"Workbench session {body.session_id} not found")

    # Warn if no project is attached — code phases will produce artifacts but
    # files won't land on disk. Not a hard failure because pure analysis
    # pipelines can still be useful without a project.
    if not session.project_path:
        logger.warning(
            f"Pipeline created for session {body.session_id} WITHOUT a project_path. "
            f"Code phases will produce artifacts but files won't be written to disk. "
            f"Attach the session to a project for the full workflow."
        )

    # Apply per-phase model overrides if provided
    overrides = body.model_overrides or {}
    for phase in template_phases:
        if phase["name"] in overrides:
            phase["model"] = overrides[phase["name"]]
        else:
            phase["model"] = phase.get("default_model")
        # Inject stacked method prompts into each phase so secondary methods
        # (e.g., GTrack "commit after every change") apply to all phases.
        if stacked_prompt:
            existing = phase.get("system_prompt", "")
            phase["system_prompt"] = f"{existing}\n\n---\n\n# Additional method instructions (from stack)\n{stacked_prompt}"

    # Create Pipeline row
    pipeline_id = str(uuid.uuid4())
    pipeline = Pipeline(
        id=pipeline_id,
        session_id=body.session_id,
        method_id=effective_method_id,
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

    # Kick off all root phases (phases with no dependencies)
    await _advance_to_next(pipeline_id)

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
async def approve_phase(
    pipeline_id: str,
    body: PipelineApprove,
    phase_index: Optional[int] = None,
    phase_run_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Approve a phase and advance the pipeline.

    With parallel execution multiple phases may be awaiting approval
    simultaneously.  Use ``phase_index`` or ``phase_run_id`` query params to
    target a specific phase; if omitted, falls back to the first
    awaiting_approval run found (backward-compat).
    """
    from app.models.pipeline import Pipeline, PhaseRun
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    # Build query for the awaiting_approval PhaseRun
    q = (
        select(PhaseRun)
        .where(PhaseRun.pipeline_id == pipeline_id)
        .where(PhaseRun.status == "awaiting_approval")
    )
    if phase_run_id:
        q = q.where(PhaseRun.id == phase_run_id)
    elif phase_index is not None:
        q = q.where(PhaseRun.phase_index == phase_index)
    else:
        # Backward-compat: try current_phase_index first, then any
        q = q.order_by(PhaseRun.phase_index)
    q = q.order_by(desc(PhaseRun.created_at)).limit(1)

    pr = (await db.execute(q)).scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="No phase awaiting approval")

    approved_index = pr.phase_index
    pr.status = "approved"
    if body.feedback:
        pr.user_feedback = body.feedback
    await db.commit()

    _push(pipeline_id, "phase_approved", phase_index=approved_index, feedback=body.feedback)

    # Advance — launch any phases whose deps are now met
    await _advance_to_next(pipeline_id)

    return {"ok": True, "approved_phase": approved_index}


@router.post("/{pipeline_id}/reject", dependencies=[Depends(verify_api_key)])
async def reject_phase(
    pipeline_id: str,
    body: PipelineReject,
    phase_index: Optional[int] = None,
    phase_run_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Reject a phase with feedback — re-runs the same phase.

    Supports ``phase_index`` or ``phase_run_id`` query params to target a
    specific phase when multiple are awaiting approval in parallel.
    """
    from app.models.pipeline import Pipeline, PhaseRun
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    q = (
        select(PhaseRun)
        .where(PhaseRun.pipeline_id == pipeline_id)
        .where(PhaseRun.status == "awaiting_approval")
    )
    if phase_run_id:
        q = q.where(PhaseRun.id == phase_run_id)
    elif phase_index is not None:
        q = q.where(PhaseRun.phase_index == phase_index)
    else:
        q = q.order_by(PhaseRun.phase_index)
    q = q.order_by(desc(PhaseRun.created_at)).limit(1)

    pr = (await db.execute(q)).scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="No phase awaiting approval")

    rejected_index = pr.phase_index
    pr.status = "rejected"
    pr.user_feedback = body.feedback
    await db.commit()

    _push(pipeline_id, "phase_rejected", phase_index=rejected_index, feedback=body.feedback)

    # Bake the rejection feedback into the phase's system prompt for the re-run
    try:
        phases = list(p.phases or [])
        if 0 <= rejected_index < len(phases):
            original = phases[rejected_index].get("system_prompt", "")
            feedback_block = (f"\n\n# User rejected your previous attempt — feedback:\n"
                              f"{body.feedback}\n\nAddress this feedback in your next attempt.")
            if feedback_block not in original:
                phases[rejected_index]["system_prompt"] = original + feedback_block
            await _db_update_pipeline(pipeline_id, phases=phases, status="running")
    except Exception as e:
        logger.warning(f"Could not inject rejection feedback: {e}")

    # Re-run the same phase
    asyncio.create_task(_run_phase(pipeline_id, rejected_index))

    return {"ok": True, "re_running_phase": rejected_index}


@router.post("/{pipeline_id}/skip", dependencies=[Depends(verify_api_key)])
async def skip_phase(
    pipeline_id: str,
    body: PipelineSkip,
    phase_index: Optional[int] = None,
    phase_run_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Skip a phase and advance the pipeline.

    Supports ``phase_index`` or ``phase_run_id`` query params to target a
    specific phase when multiple are running in parallel.
    """
    from app.models.pipeline import Pipeline, PhaseRun
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if p.status not in ("awaiting_approval", "running"):
        raise HTTPException(status_code=409,
                            detail=f"Pipeline cannot skip from status={p.status}")

    # Find the phase run to skip
    q = (
        select(PhaseRun)
        .where(PhaseRun.pipeline_id == pipeline_id)
        .where(PhaseRun.status.in_(("running", "awaiting_approval")))
    )
    if phase_run_id:
        q = q.where(PhaseRun.id == phase_run_id)
    elif phase_index is not None:
        q = q.where(PhaseRun.phase_index == phase_index)
    else:
        q = q.order_by(PhaseRun.phase_index)
    q = q.order_by(desc(PhaseRun.created_at)).limit(1)

    pr = (await db.execute(q)).scalar_one_or_none()
    skipped_index = pr.phase_index if pr else (phase_index or p.current_phase_index)
    if pr:
        pr.status = "skipped"
        if body.reason:
            pr.user_feedback = body.reason
        await db.commit()

    _push(pipeline_id, "phase_skipped", phase_index=skipped_index, reason=body.reason)

    await _advance_to_next(pipeline_id)
    return {"ok": True, "skipped_phase": skipped_index}


@router.post("/{pipeline_id}/retry", dependencies=[Depends(verify_api_key)])
async def retry_phase(
    pipeline_id: str,
    phase_index: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """Retry failed phase(s).

    If ``phase_index`` is given, retry that specific phase.  Otherwise retry
    all failed phases whose dependencies are met (enables parallel retry).
    """
    from app.models.pipeline import Pipeline, PhaseRun
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if p.status not in ("failed", "cancelled"):
        raise HTTPException(status_code=409,
                            detail=f"Can only retry from failed/cancelled (status={p.status})")

    # Reset pipeline status
    await _db_update_pipeline(pipeline_id, status="running", completed_at=None)

    if phase_index is not None:
        # Retry a single specific phase
        _push(pipeline_id, "pipeline_retry", phase_index=phase_index,
              message=f"Retrying phase {phase_index}")
        asyncio.create_task(_run_phase(pipeline_id, phase_index))
        return {"ok": True, "retrying_phase": phase_index}

    # Retry all failed phases whose deps are met — let _advance_to_next
    # figure it out after we clear the failed PhaseRun records so they
    # don't block re-evaluation.
    failed_runs = (await db.execute(
        select(PhaseRun)
        .where(PhaseRun.pipeline_id == pipeline_id)
        .where(PhaseRun.status == "failed")
    )).scalars().all()

    retried_indices = []
    for fr in failed_runs:
        # Delete the failed run so _advance_to_next sees the phase as
        # pending and will re-launch it if deps are met.
        await db.delete(fr)
        retried_indices.append(fr.phase_index)
    await db.commit()

    _push(pipeline_id, "pipeline_retry", phase_index=retried_indices[0] if retried_indices else 0,
          message=f"Retrying failed phases: {retried_indices}")

    await _advance_to_next(pipeline_id)
    return {"ok": True, "retrying_phases": retried_indices}


@router.post("/{pipeline_id}/cancel", dependencies=[Depends(verify_api_key)])
async def cancel_pipeline(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.pipeline import Pipeline
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    await _db_update_pipeline(pipeline_id, status="cancelled", completed_at=datetime.utcnow())
    _push(pipeline_id, "pipeline_done", message="Pipeline cancelled.", status="cancelled")
    return {"ok": True}


@router.delete("/{pipeline_id}", dependencies=[Depends(verify_api_key)])
async def delete_pipeline(pipeline_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a single pipeline and all its phase runs. Session is NOT deleted."""
    from app.models.pipeline import Pipeline, PhaseRun
    p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    # Delete phase runs
    runs = (await db.execute(select(PhaseRun).where(PhaseRun.pipeline_id == pipeline_id))).scalars().all()
    for r in runs:
        await db.delete(r)
    await db.delete(p)
    await db.commit()
    _queues.pop(pipeline_id, None)
    _event_logs.pop(pipeline_id, None)
    return {"ok": True, "deleted_phase_runs": len(runs)}


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
