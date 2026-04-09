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
async def _run_phase(pipeline_id: str, phase_index: int, retry_count: int = 0, max_retries: int = 0):
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

    # Resolve max_retries from phase_def if not passed explicitly
    if max_retries == 0:
        max_retries = phase_def.get("max_retries", 0)

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
            retry_count=retry_count,
            max_retries=max_retries,
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

    # ── Auto-retry with feedback: check if this reviewer phase rejected ────────
    # If the phase has on_failure="retry_with_feedback" and the output contains
    # a rejection verdict, automatically re-run the upstream phase with
    # the reviewer's feedback injected as context.
    auto_retry_triggered = False
    if phase_def.get("on_failure") == "retry_with_feedback":
        rejection_verdict = False
        feedback_text = ""
        try:
            artifact_data = artifact.get("data") if artifact.get("type") == "json" else None
            if artifact_data and isinstance(artifact_data, dict):
                verdict = str(artifact_data.get("overall_verdict", artifact_data.get("verdict", ""))).lower().strip()
                if verdict in ("reject", "rejected", "fail", "failed", "needs_changes"):
                    rejection_verdict = True
                    # Extract feedback details from the artifact
                    feedback_parts = []
                    issues = artifact_data.get("issues", [])
                    if issues and isinstance(issues, list):
                        for issue in issues:
                            if isinstance(issue, dict):
                                sev = issue.get("severity", "")
                                desc = issue.get("description", "")
                                suggestion = issue.get("suggestion", "")
                                file_ref = issue.get("file", "")
                                parts = [f"[{sev}]" if sev else ""]
                                if file_ref:
                                    parts.append(f"in {file_ref}")
                                parts.append(desc)
                                if suggestion:
                                    parts.append(f"Suggestion: {suggestion}")
                                feedback_parts.append(" ".join(p for p in parts if p))
                            elif isinstance(issue, str):
                                feedback_parts.append(issue)
                    missing = artifact_data.get("missing_from_spec", [])
                    if missing:
                        feedback_parts.append("Missing from spec: " + ", ".join(str(m) for m in missing))
                    security = artifact_data.get("security_concerns", [])
                    if security:
                        feedback_parts.append("Security concerns: " + ", ".join(str(s) for s in security))
                    gaps = artifact_data.get("gaps", [])
                    if gaps:
                        feedback_parts.append("Gaps: " + ", ".join(str(g) for g in gaps))
                    recommendations = artifact_data.get("recommendations", [])
                    if recommendations:
                        feedback_parts.append("Recommendations: " + ", ".join(str(r) for r in recommendations))

                    feedback_text = "\n".join(feedback_parts) if feedback_parts else f"Reviewer verdict: {verdict}"
        except Exception as e:
            logger.warning(f"Failed to parse reviewer output for auto-retry: {e}")

        if rejection_verdict and feedback_text:
            # Persist this reviewer run as "rejected" (it produced a rejection verdict)
            await _db_update_phase(
                phase_run_id,
                status="rejected",
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
                status="rejected",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            # Determine the upstream phase to retry (the one right before this reviewer)
            upstream_index = phase_def.get("retry_target", phase_index - 1)
            if upstream_index < 0:
                upstream_index = 0

            # Count existing retries for the upstream phase
            retry_max = phase_def.get("max_retries", 2)
            async with AsyncSessionLocal() as db:
                from sqlalchemy import func as sqlfunc
                existing_retries = (await db.execute(
                    select(sqlfunc.count(PhaseRun.id))
                    .where(PhaseRun.pipeline_id == pipeline_id)
                    .where(PhaseRun.phase_index == upstream_index)
                    .where(PhaseRun.retry_count > 0)
                )).scalar() or 0
                # The actual retry count is the number of retry runs already done
                current_retry_count = existing_retries

            auto_retry_triggered = await _retry_upstream_with_feedback(
                pipeline_id=pipeline_id,
                reviewer_phase_index=phase_index,
                upstream_phase_index=upstream_index,
                feedback_text=feedback_text,
                retry_count=current_retry_count,
                max_retries=retry_max,
            )

    # ── Normal flow (no auto-retry triggered) ─────────────────────────────────
    if not auto_retry_triggered:
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


async def _retry_upstream_with_feedback(
    pipeline_id: str,
    reviewer_phase_index: int,
    upstream_phase_index: int,
    feedback_text: str,
    retry_count: int,
    max_retries: int,
) -> bool:
    """Re-run an upstream phase with reviewer feedback injected.

    Returns True if retry was initiated, False if max_retries exhausted
    (pipeline pauses for manual approval in that case).
    """
    from app.models.pipeline import Pipeline, PhaseRun

    # Check if retries exhausted
    if retry_count >= max_retries:
        logger.info(
            f"Pipeline {pipeline_id}: max retries ({max_retries}) exhausted "
            f"for phase {upstream_phase_index}. Pausing for manual approval."
        )
        await _db_update_pipeline(pipeline_id, status="awaiting_approval")
        _push(
            pipeline_id, "phase_retry_exhausted",
            phase_index=upstream_phase_index,
            phase_name="",  # filled below
            retry_count=retry_count,
            max_retries=max_retries,
            message=f"Phase has been retried {retry_count} time(s) without passing review. Manual approval required.",
        )
        # Update the event with the actual phase name
        async with AsyncSessionLocal() as db:
            p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
            if p and p.phases and upstream_phase_index < len(p.phases):
                phase_name = p.phases[upstream_phase_index].get("name", f"Phase {upstream_phase_index}")
                _push(
                    pipeline_id, "awaiting_approval",
                    phase_index=upstream_phase_index,
                    message=f"Phase '{phase_name}' failed review after {retry_count} retries. Awaiting manual approval.",
                )
        return False

    # Inject feedback into the upstream phase's system prompt
    async with AsyncSessionLocal() as db:
        p = (await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))).scalar_one_or_none()
        if not p:
            return False

        phases = list(p.phases or [])
        if upstream_phase_index >= len(phases):
            return False

        upstream_phase = phases[upstream_phase_index]
        phase_name = upstream_phase.get("name", f"Phase {upstream_phase_index}")

        # Add retry feedback block to the upstream phase's system prompt
        feedback_block = (
            f"\n\n# Retry attempt {retry_count + 1}/{max_retries} — Reviewer feedback from previous attempt:\n"
            f"{feedback_text}\n\n"
            f"Address ALL the reviewer's feedback in this revision. This is retry {retry_count + 1} of {max_retries}."
        )
        # Remove any prior retry feedback blocks to avoid accumulation
        original_prompt = upstream_phase.get("system_prompt", "")
        # Strip previous retry blocks if present
        import re as _re
        original_prompt = _re.sub(
            r'\n\n# Retry attempt \d+/\d+ — Reviewer feedback from previous attempt:.*?'
            r'This is retry \d+ of \d+\.',
            '', original_prompt, flags=re.DOTALL
        )
        phases[upstream_phase_index]["system_prompt"] = original_prompt + feedback_block

        # Update pipeline: rewind to upstream phase
        p.phases = phases
        p.current_phase_index = upstream_phase_index
        p.status = "running"
        await db.commit()

    new_retry = retry_count + 1
    feedback_summary = feedback_text[:200] + ("..." if len(feedback_text) > 200 else "")
    _push(
        pipeline_id, "phase_retry",
        phase_index=upstream_phase_index,
        phase_name=phase_name,
        retry_count=new_retry,
        max_retries=max_retries,
        feedback_summary=feedback_summary,
        message=f"Retrying phase '{phase_name}' with reviewer feedback (attempt {new_retry}/{max_retries}).",
    )

    logger.info(
        f"Pipeline {pipeline_id}: retrying phase {upstream_phase_index} ({phase_name}) "
        f"with feedback — attempt {new_retry}/{max_retries}"
    )

    # Run the upstream phase again
    asyncio.create_task(_run_phase(pipeline_id, upstream_phase_index, retry_count=new_retry, max_retries=max_retries))
    return True


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
    from app.services.phase_templates import get_phases_for_method, list_supported_methods

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
