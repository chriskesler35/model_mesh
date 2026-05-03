"""Chat completion endpoints."""

import uuid
import json
import time
import asyncio
from typing import Any, Dict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_memory
from app.models import Conversation, Message
from app.schemas import ChatCompletionRequest
from app.services import PersonaResolver, Router, model_client
from app.services.memory_context import MemoryContext
from app.middleware.auth import verify_api_key
from app.middleware.rate_limit import check_rate_limit
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["chat"], dependencies=[Depends(verify_api_key), Depends(check_rate_limit)])

# Ephemeral per-conversation workflow gating state.
# Keyed by conversation_id string.
_workflow_session_state: Dict[str, Dict[str, Any]] = {}


def _get_workflow_state(conversation_id: str) -> Dict[str, Any]:
    state = _workflow_session_state.get(conversation_id)
    if state is None:
        state = {
            "chat_only": False,              # user said scope does NOT warrant a project
            "scope_prompt_pending": False,   # awaiting yes/no for "project or regular chat?"
            "pending_trigger": None,         # cached trigger match while waiting for yes/no
        }
        _workflow_session_state[conversation_id] = state
    return state


def _system_completion(
    *,
    content: str,
    conversation_id: str,
    actual_model: str,
    workflow_trigger: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    modelmesh: Dict[str, Any] = {
        "persona_used": "system",
        "actual_model": actual_model,
        "estimated_cost": 0.0,
        "provider": "system",
    }
    if workflow_trigger is not None:
        modelmesh["workflow_trigger"] = workflow_trigger

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "conversation_id": conversation_id,
        "model": "system",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "modelmesh": modelmesh,
    }


@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    db: AsyncSession = Depends(get_db),
    memory = Depends(get_memory)
):
    """OpenAI-compatible chat completions endpoint."""

    # Resolve conversation ID early so workflow gating state can persist per chat session.
    conv_id = str(request.conversation_id) if request.conversation_id else str(uuid.uuid4())

    # 0. Check for chat commands (model management, help, etc.)
    last_user_msg = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        None,
    )
    if last_user_msg:
        from app.services.chat_command_parser import parse_chat_command
        parsed_command = parse_chat_command(last_user_msg)
        if parsed_command:
            from app.services.chat_commands.dispatcher import dispatch_command
            command_response = await dispatch_command(
                parsed_command, db, conversation_id=conv_id,
            )
            logger.info(f"Chat command handled: {parsed_command['action']} {parsed_command['entity_type']}")
            return _system_completion(
                content=command_response,
                conversation_id=conv_id,
                actual_model="command_executor",
            )

        # No explicit command matched — check for workflow triggers
        from app.services.chat_commands.workflow_commands import (
            detect_workflow_trigger,
            handle_workflow_trigger,
            handle_suggest_pipeline,
            is_affirmative_reply,
            is_negative_reply,
            is_explicit_project_intent,
        )
        wf_state = _get_workflow_state(conv_id)

        # If we previously asked whether this should become a project, consume yes/no.
        if wf_state.get("scope_prompt_pending"):
            if is_negative_reply(last_user_msg):
                wf_state["chat_only"] = True
                wf_state["scope_prompt_pending"] = False
                wf_state["pending_trigger"] = None
                return _system_completion(
                    content=(
                        "Understood. I'll keep this conversation in regular chat mode and won't "
                        "start a project workflow unless you explicitly ask to start one."
                    ),
                    conversation_id=conv_id,
                    actual_model="workflow_detector",
                )
            if is_affirmative_reply(last_user_msg):
                pending_trigger = wf_state.get("pending_trigger")
                wf_state["chat_only"] = False
                wf_state["scope_prompt_pending"] = False
                wf_state["pending_trigger"] = None
                if pending_trigger:
                    suggestion = await handle_workflow_trigger(
                        last_user_msg, pending_trigger, db, conversation_id=conv_id,
                    )
                    return _system_completion(
                        content=suggestion,
                        conversation_id=conv_id,
                        actual_model="workflow_detector",
                        workflow_trigger=pending_trigger,
                    )

        explicit_project_intent = is_explicit_project_intent(last_user_msg)
        if not (wf_state.get("chat_only") and not explicit_project_intent):
            trigger_match = await detect_workflow_trigger(last_user_msg, db)
            if trigger_match:
                # Explicit intent -> offer workflow immediately.
                if explicit_project_intent:
                    suggestion = await handle_workflow_trigger(
                        last_user_msg, trigger_match, db, conversation_id=conv_id,
                    )
                    return _system_completion(
                        content=suggestion,
                        conversation_id=conv_id,
                        actual_model="workflow_detector",
                        workflow_trigger=trigger_match,
                    )

                # Non-explicit request -> ask if this should be project-scoped first.
                wf_state["scope_prompt_pending"] = True
                wf_state["pending_trigger"] = trigger_match
                return _system_completion(
                    content=(
                        "This could be handled as a full project workflow. "
                        "Do you want to treat this as a project?\n\n"
                        "Reply **yes** to use project workflow, or **no** to keep regular chat mode for this session."
                    ),
                    conversation_id=conv_id,
                    actual_model="workflow_detector",
                    workflow_trigger=trigger_match,
                )

            # Suggest pipeline only for explicit project intent language.
            pipeline_suggestion = await handle_suggest_pipeline(
                last_user_msg, db, conversation_id=conv_id,
            )
            if pipeline_suggestion:
                return _system_completion(
                    content=pipeline_suggestion,
                    conversation_id=conv_id,
                    actual_model="workflow_detector",
                )

    # 1. Resolve persona
    resolver = PersonaResolver(db)
    persona, primary_model, fallback_model = await resolver.resolve(request.model)
    
    # Apply model override if specified (user picked a specific model from dropdown)
    if request.model_override and persona:
        from app.models.model import Model as ModelORM
        from app.models.provider import Provider as ProviderORM
        from app.services.codex_oauth import should_use_codex_oauth_proxy
        from sqlalchemy import case, or_
        _use_codex_proxy = should_use_codex_oauth_proxy()
        # Try exact match first, then partial/fuzzy on the tail segment of the model_id.
        _override_ref = request.model_override
        _last_part = _override_ref.split("/")[-1]  # e.g. "gpt-4.5" from "openai/gpt-4.5"
        override_result = await db.execute(
            select(ModelORM, ProviderORM)
            .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
            .where(ModelORM.is_active == True)
            .where(
                or_(
                    ModelORM.model_id == _override_ref,
                    ModelORM.model_id.contains(_last_part),
                )
            )
            .order_by(
                # Exact match first
                (ModelORM.model_id == _override_ref).desc(),
                # Deprioritise openai-codex when no proxy is configured
                case(
                    (ProviderORM.name == "openai-codex", 0 if _use_codex_proxy else -1),
                    else_=1,
                ).desc(),
                ModelORM.validated_at.desc().nulls_last(),
            )
            .limit(1)
        )
        override_row = override_result.first()
        if override_row:
            primary_model = override_row[0]
            fallback_model = None  # No fallback when explicitly overridden
            logger.info(f"Model override resolved: requested='{_override_ref}' -> matched='{primary_model.model_id}' via provider='{override_row[1].name}'")
        else:
            logger.warning(
                f"Model override '{_override_ref}' not found or inactive in DB; "
                "continuing with persona's assigned model"
            )
    
    if not persona:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "type": "invalid_request_error",
                    "message": f"Persona not found: {request.model}",
                    "code": "persona_not_found"
                }
            }
        )
    
    # If no model assigned, try to get a default model
    if not primary_model:
        # Get first active model as fallback
        from app.models import Model
        result = await db.execute(
            select(Model).where(Model.is_active == True).limit(1)
        )
        primary_model = result.scalar_one_or_none()
        
        if not primary_model:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": {
                        "type": "model_error",
                        "message": "No models available. Please add a model to use chat.",
                        "code": "no_models_available"
                    }
                }
            )
    
    # 2. Handle conversation ID
    conversation_id = conv_id
    if request.conversation_id is None:
        # Auto-title from first user message
        first_user = next((m.content for m in request.messages if m.role == "user"), None)
        auto_title = None
        if first_user:
            auto_title = first_user[:60] + ("…" if len(first_user) > 60 else "")
        # Create conversation record
        conv = Conversation(
            id=uuid.UUID(conversation_id),
            persona_id=persona.id,
            title=auto_title,
            last_message_at=datetime.now(timezone.utc),
            message_count=len(request.messages),
        )
        db.add(conv)
        await db.commit()
        logger.info(f"Chat created conversation {conversation_id[:8]}… title={auto_title!r}")

    # 3. Route request
    router_service = Router(db, memory)
    
    if request.stream:
        return await _stream_response(
            router_service, persona, primary_model, fallback_model,
            request, conversation_id, db
        )
    else:
        return await _sync_response(
            router_service, persona, primary_model, fallback_model,
            request, conversation_id, db
        )


async def _stream_response(
    router_service, persona, primary_model, fallback_model,
    request, conversation_id, db
):
    """Handle streaming response."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"

    async def generate():
        try:
            start_time = time.time()
            full_content = ""

            # Convert messages to dict
            msg_dicts = [{"role": m.role, "content": m.content} for m in request.messages]

            # Inject unified identity/soul/user/method context (shared with workbench)
            try:
                from app.services.identity_context import build_identity_context
                identity_block = build_identity_context(include_method=True)
                if identity_block:
                    msg_dicts.insert(0, {"role": "system", "content": identity_block})
            except Exception as _e:
                logger.warning(f"Failed to inject identity context: {_e}")

            # Inject memory context into system prompt if enabled
            if persona.memory_enabled:
                try:
                    memory_context = MemoryContext(db)
                    injected_prompt = await memory_context.inject_context(
                        persona.system_prompt or "You are a helpful assistant.",
                        persona.name
                    )
                    # Prepend system message with context
                    msg_dicts.insert(0, {"role": "system", "content": injected_prompt})
                except Exception as e:
                    logger.warning(f"Failed to inject memory context: {e}")
                    # Continue without context

            # Get the async generator from router
            response_stream = await router_service.route_request(
                persona, primary_model, fallback_model,
                msg_dicts, conversation_id, stream=True,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            )

            async for chunk in response_stream:
                # Parse LiteLLM chunk and format as OpenAI SSE
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    content = delta.content if hasattr(delta, 'content') else None

                    if content:
                        full_content += content
                        data = json.dumps({
                            "id": completion_id,
                            "object": "chat.completion.chunk", "conversation_id": conversation_id,
                            "model": primary_model.model_id if primary_model else "unknown",
                            "choices": [{
                                "index": 0,
                                "delta": {"content": content},
                                "finish_reason": None
                            }]
                        })
                        yield f"data: {data}\n\n"

            # Send done
            yield "data: [DONE]\n\n"

            # Log request with estimated tokens
            latency_ms = int((time.time() - start_time) * 1000)
            input_tokens = model_client.estimate_tokens(msg_dicts, primary_model) if primary_model else 0
            # Estimate output tokens from content (rough: ~4 chars per token)
            output_tokens = len(full_content) // 4 if full_content else 0
            estimated_cost = model_client.estimate_cost(input_tokens, output_tokens, primary_model) if primary_model else 0.0

            await _log_request(db, conversation_id, persona.id,
                              primary_model.id if primary_model else None,
                              primary_model.provider_id if primary_model else None,
                              input_tokens, output_tokens, latency_ms, True, None,
                              estimated_cost=estimated_cost)
            await _update_conversation_meta(db, conversation_id)
            # Persist messages to DB
            user_text = next((m['content'] for m in reversed(msg_dicts) if m['role'] == 'user'), '')
            if user_text and full_content:
                await _save_messages(db, conversation_id, user_text, full_content,
                                     model_id=primary_model.id if primary_model else None,
                                     input_tokens=input_tokens, output_tokens=output_tokens,
                                     latency_ms=latency_ms, estimated_cost=estimated_cost)

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            error_data = json.dumps({
                "error": {
                    "type": "model_error",
                    "message": str(e),
                    "code": "streaming_error"
                }
            })
            yield f"data: {error_data}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


async def _sync_response(
    router_service, persona, primary_model, fallback_model,
    request, conversation_id, db
):
    """Handle synchronous response."""
    start_time = time.time()

    try:
        # Convert messages to dict
        msg_dicts = [{"role": m.role, "content": m.content} for m in request.messages]

        # Validate we have messages
        if not msg_dicts:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Messages cannot be empty",
                        "code": "invalid_messages"
                    }
                }
            )

        # Inject unified identity/soul/user/method context (shared with workbench)
        try:
            from app.services.identity_context import build_identity_context
            identity_block = build_identity_context(include_method=True)
            if identity_block:
                msg_dicts.insert(0, {"role": "system", "content": identity_block})
        except Exception as _e:
            logger.warning(f"Failed to inject identity context: {_e}")

        # Inject memory context into system prompt if enabled
        if persona.memory_enabled:
            try:
                memory_context = MemoryContext(db)
                injected_prompt = await memory_context.inject_context(
                    persona.system_prompt or "You are a helpful assistant.",
                    persona.name
                )
                # Prepend system message with context
                msg_dicts.insert(0, {"role": "system", "content": injected_prompt})
            except Exception as e:
                logger.warning(f"Failed to inject memory context: {e}")
                # Continue without context

        # Get response from router (non-streaming returns a dict/object).
        # Bound request time to keep chat responsive when upstream model calls stall.
        response = None
        full_content = ""
        input_tokens = 0
        output_tokens = 0
        llm_timeout_fallback = False

        try:
            response = await asyncio.wait_for(
                router_service.route_request(
                    persona, primary_model, fallback_model,
                    msg_dicts, conversation_id, stream=False,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens
                ),
                timeout=45,
            )
        except asyncio.TimeoutError:
            llm_timeout_fallback = True
            logger.warning("Sync chat completion timed out for conversation %s", conversation_id)
            full_content = (
                "I’m still processing that and hit a response timeout. "
                "Please try again, or break the request into smaller steps."
            )

        # Extract content and usage from LiteLLM response when available.
        if not llm_timeout_fallback and response is not None:
            if hasattr(response, 'choices') and response.choices and len(response.choices) > 0:
                choice = response.choices[0]
                if hasattr(choice, 'message') and choice.message:
                    full_content = choice.message.content or ""
                else:
                    logger.warning(f"Unexpected response format: {response}")
                    full_content = str(response)
            else:
                logger.warning(f"No choices in response: {response}")
                # Try to extract content from raw response
                if hasattr(response, 'content'):
                    full_content = response.content or ""
                elif isinstance(response, str):
                    full_content = response
                else:
                    full_content = "No response generated"

            # Extract actual token usage if available
            if hasattr(response, 'usage') and response.usage:
                input_tokens = response.usage.prompt_tokens or 0
                output_tokens = response.usage.completion_tokens or 0

        # Fallback token estimation (also used by timeout fallback path)
        if input_tokens == 0 and output_tokens == 0:
            input_tokens = model_client.estimate_tokens(msg_dicts, primary_model) if primary_model else 0
            output_tokens = len(full_content) // 4 if full_content else 0

        # Calculate cost
        estimated_cost = model_client.estimate_cost(input_tokens, output_tokens, primary_model) if primary_model else 0.0

        latency_ms = int((time.time() - start_time) * 1000)

        # Log request with actual tokens
        await _log_request(db, conversation_id, persona.id,
                          primary_model.id if primary_model else None,
                          primary_model.provider_id if primary_model else None,
                          input_tokens, output_tokens, latency_ms, True, None,
                          estimated_cost=estimated_cost)
        await _update_conversation_meta(db, conversation_id)
        # Persist messages to DB
        user_text = next((m['content'] for m in reversed(msg_dicts) if m['role'] == 'user'), '')
        if user_text and full_content:
            await _save_messages(db, conversation_id, user_text, full_content,
                                 model_id=primary_model.id if primary_model else None,
                                 input_tokens=input_tokens, output_tokens=output_tokens,
                                 latency_ms=latency_ms, estimated_cost=estimated_cost)

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "conversation_id": conversation_id,
            "model": primary_model.model_id if primary_model else "unknown",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": full_content
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens
            },
            "modelmesh": {
                "persona_used": persona.name,
                "actual_model": primary_model.model_id if primary_model else "unknown",
                "estimated_cost": round(estimated_cost, 6),
                "provider": "ollama"  # Simplified - avoid lazy loading
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync response error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "type": "model_error",
                    "message": str(e),
                    "code": "model_error"
                }
            }
        )


async def _save_messages(db, conversation_id: str, user_content: str, assistant_content: str,
                         model_id=None, input_tokens=0, output_tokens=0, latency_ms=0, estimated_cost=0.0):
    """Persist user + assistant messages to the database and write a context snapshot."""
    from app.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as fresh_db:
            conv_str = str(conversation_id)
            model_str = str(model_id) if model_id else None
            user_msg = Message(
                conversation_id=conv_str,
                role="user",
                content=user_content,
            )
            fresh_db.add(user_msg)
            asst_msg = Message(
                conversation_id=conv_str,
                role="assistant",
                content=assistant_content,
                model_used=model_str,
                tokens_in=input_tokens,
                tokens_out=output_tokens,
                latency_ms=latency_ms,
                estimated_cost=estimated_cost,
            )
            fresh_db.add(asst_msg)
            await fresh_db.commit()
            logger.info(f"Saved messages for conv {conversation_id[:8]}")

            # Check for @mentions and create notifications
            try:
                from app.services.mentions import extract_mentions
                from app.routes.collaboration import get_user_by_username
                from app.models.notification import Notification
                from app.services.ws_manager import manager

                mentioned_usernames = extract_mentions(user_content)
                for username in mentioned_usernames:
                    target_user = get_user_by_username(username)
                    if not target_user:
                        continue
                    target_id = target_user.get("id", "")
                    preview = user_content[:120] + ("…" if len(user_content) > 120 else "")
                    notif = Notification(
                        user_id=target_id,
                        type="mention",
                        title=f"You were mentioned in a conversation",
                        message=preview,
                        conversation_id=conv_str,
                        message_id=str(user_msg.id),
                    )
                    fresh_db.add(notif)
                    # Push real-time notification via WebSocket
                    try:
                        import asyncio as _ws_asyncio
                        _ws_asyncio.create_task(manager.send_to_user(target_id, {
                            "type": "notification",
                            "payload": notif.to_dict(),
                        }))
                    except Exception:
                        pass  # WebSocket push is best-effort
                if mentioned_usernames:
                    await fresh_db.commit()
                    logger.info(f"Created {len(mentioned_usernames)} mention notification(s) in conv {conversation_id[:8]}")
            except Exception as mention_err:
                logger.warning(f"Mention processing failed (non-fatal): {mention_err}")

            # Write context snapshot — load all messages for this conversation
            try:
                from sqlalchemy import select as _select
                from app.models import Message as _Msg, Conversation as _Conv
                from app.services.context_snapshot import write_snapshot, maybe_distill_memory

                # Fetch conversation title + all messages
                conv = await fresh_db.get(_Conv, uuid.UUID(conv_str))
                title = conv.title if conv else ""

                all_msgs_result = await fresh_db.execute(
                    _select(_Msg)
                    .where(_Msg.conversation_id == conv_str)
                    .order_by(_Msg.created_at)
                )
                all_msgs = all_msgs_result.scalars().all()
                msg_dicts = [{"role": m.role, "content": m.content} for m in all_msgs]

                # Resolve model name
                model_name = None
                if model_id:
                    from app.models import Model as _Model
                    m_obj = await fresh_db.get(_Model, model_id)
                    model_name = m_obj.model_id if m_obj else str(model_id)

                write_snapshot(
                    conversation_id=conv_str,
                    title=title or "",
                    messages=msg_dicts,
                    model_name=model_name or "",
                )

                # Periodically distill memory from the conversation
                import asyncio as _asyncio
                _asyncio.create_task(maybe_distill_memory(
                    conversation_id=conv_str,
                    messages=msg_dicts,
                    model_name=model_name or "",
                    message_count=len(all_msgs),
                ))

                # Periodically detect preferences (every 10 messages)
                if len(all_msgs) > 0 and len(all_msgs) % 10 == 0:
                    _asyncio.create_task(_maybe_detect_preferences(msg_dicts[-20:]))

            except Exception as snap_err:
                logger.warning(f"Snapshot write failed (non-fatal): {snap_err}")

    except Exception as e:
        logger.error(f"Failed to save messages for conv {conversation_id}: {e}", exc_info=True)


async def _maybe_detect_preferences(messages: list[dict]):
    """Background task: use LLM to detect preferences from recent messages."""
    try:
        import json
        from app.database import AsyncSessionLocal
        from app.models.preference import Preference
        from app.services.model_client import ModelClient
        from app.models.model import Model as ModelORM
        from app.models.provider import Provider as ProviderORM
        from sqlalchemy import select as _sel

        async with AsyncSessionLocal() as db:
            # Use first active local model (cheap/fast)
            result = await db.execute(
                _sel(ModelORM, ProviderORM)
                .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
                .where(ProviderORM.name.ilike("%ollama%"))
                .where(ModelORM.is_active == True)
                .limit(1)
            )
            row = result.first()
            if not row:
                # Fallback to any active model
                result = await db.execute(
                    _sel(ModelORM, ProviderORM)
                    .join(ProviderORM, ModelORM.provider_id == ProviderORM.id)
                    .where(ModelORM.is_active == True)
                    .limit(1)
                )
                row = result.first()
            if not row:
                return

            model_orm, provider_orm = row
            conv_text = "\n".join(f"{m.get('role','user').upper()}: {m.get('content','')}" for m in messages)

            detect_prompt = (
                "Analyze this conversation and extract user preferences the AI should remember. "
                "Return ONLY a JSON array of objects with keys: key (snake_case), value (one sentence), "
                "category (general|coding|communication|ui|workflow). "
                "If none found, return []. Do NOT invent preferences."
            )

            client = ModelClient()
            response = await client.call_model(
                model=model_orm, provider=provider_orm,
                messages=[
                    {"role": "system", "content": detect_prompt + "\n\n" + conv_text},
                    {"role": "user", "content": "Extract preferences. JSON array only."},
                ],
                stream=False, temperature=0.1, max_tokens=500,
            )

            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            detected = json.loads(raw)
            if not isinstance(detected, list):
                return

            # Check existing keys
            existing = await db.execute(_sel(Preference.key))
            existing_keys = {r[0] for r in existing.fetchall()}

            saved = 0
            for item in detected:
                key = item.get("key", "").strip()
                value = item.get("value", "").strip()
                if not key or not value or key in existing_keys:
                    continue
                pref = Preference(
                    id=str(uuid.uuid4()),
                    key=key, value=value,
                    category=item.get("category", "general").strip(),
                    source="detected",
                )
                db.add(pref)
                existing_keys.add(key)
                saved += 1

            if saved:
                await db.commit()
                logger.info(f"Auto-detected {saved} new preference(s) from chat")

    except Exception as e:
        logger.debug(f"Preference detection skipped: {e}")


async def _update_conversation_meta(db, conversation_id: str, added_messages: int = 2):
    """Update last_message_at and message_count after each exchange."""
    from app.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as fresh_db:
            conv = await fresh_db.get(Conversation, uuid.UUID(str(conversation_id)))
            if conv:
                conv.last_message_at = datetime.now(timezone.utc)
                conv.message_count = (conv.message_count or 0) + added_messages
                await fresh_db.commit()
    except Exception as e:
        logger.warning(f"Failed to update conversation meta: {e}")


async def _log_request(db, conversation_id, persona_id, model_id, provider_id,
                       input_tokens, output_tokens, latency_ms, success, error_message,
                       estimated_cost=0.0):
    """Log request to database with actual token counts and cost."""
    from app.models import RequestLog

    try:
        log = RequestLog(
            conversation_id=conversation_id,
            persona_id=persona_id,
            model_id=model_id,
            provider_id=provider_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            estimated_cost=estimated_cost,
            success=success,
            error_message=error_message
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        # Don't fail the request if logging fails
        import logging
        logging.getLogger(__name__).warning(f"Failed to log request: {e}")
