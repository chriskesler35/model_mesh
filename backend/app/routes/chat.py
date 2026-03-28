"""Chat completion endpoints."""

import uuid
import json
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_memory
from app.models import Conversation
from app.schemas import ChatCompletionRequest
from app.services import PersonaResolver, Router, model_client
from app.services.memory_context import MemoryContext
from app.middleware.auth import verify_api_key
from app.middleware.rate_limit import check_rate_limit
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["chat"], dependencies=[Depends(verify_api_key), Depends(check_rate_limit)])


@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    db: AsyncSession = Depends(get_db),
    memory = Depends(get_memory)
):
    """OpenAI-compatible chat completions endpoint."""
    
    # 1. Resolve persona
    resolver = PersonaResolver(db)
    persona, primary_model, fallback_model = await resolver.resolve(request.model)
    
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
    
    # 2. Handle conversation ID
    conversation_id = request.conversation_id
    if not conversation_id:
        conversation_id = await memory.create_conversation_id()
        # Create conversation record
        conv = Conversation(id=uuid.UUID(conversation_id), persona_id=persona.id)
        db.add(conv)
        await db.commit()
    
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
                            "object": "chat.completion.chunk",
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

        # Get response from router (non-streaming returns a dict/object)
        response = await router_service.route_request(
            persona, primary_model, fallback_model,
            msg_dicts, conversation_id, stream=False,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )

        # Extract content and usage from LiteLLM response
        full_content = ""
        input_tokens = 0
        output_tokens = 0

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
        else:
            # Fallback to estimation
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

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
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