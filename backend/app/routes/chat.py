"""Chat completion endpoints."""

import uuid
import json
import time
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_memory
from app.models import Conversation, Message, RequestLog
from app.schemas import ChatCompletionRequest
from app.services import PersonaResolver, Router, model_client
from app.middleware.auth import verify_api_key
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["chat"], dependencies=[Depends(verify_api_key)])


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
            
            async for chunk in router_service.route_request(
                persona, primary_model, fallback_model,
                msg_dicts, conversation_id, stream=True,
                temperature=request.temperature,
                max_tokens=request.max_tokens
            ):
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
            
            # Log request
            latency_ms = int((time.time() - start_time) * 1000)
            await _log_request(db, conversation_id, persona.id, 
                              primary_model.id if primary_model else None, 
                              primary_model.provider_id if primary_model else None, 
                              0, 0, latency_ms, True, None)
            
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
        # Collect all chunks
        full_content = ""
        msg_dicts = [{"role": m.role, "content": m.content} for m in request.messages]
        
        async for chunk in router_service.route_request(
            persona, primary_model, fallback_model,
            msg_dicts, conversation_id, stream=False,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        ):
            if hasattr(chunk, 'choices') and chunk.choices:
                full_content += chunk.choices[0].message.content or ""
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Log request
        await _log_request(db, conversation_id, persona.id,
                          primary_model.id if primary_model else None,
                          primary_model.provider_id if primary_model else None,
                          0, 0, latency_ms, True, None)
        
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
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            },
            "modelmesh": {
                "persona_used": persona.name,
                "actual_model": primary_model.model_id if primary_model else "unknown",
                "estimated_cost": 0.0,
                "provider": "ollama"
            }
        }
        
    except Exception as e:
        logger.error(f"Sync response error: {e}")
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
                       input_tokens, output_tokens, latency_ms, success, error_message):
    """Log request to database."""
    log = RequestLog(
        conversation_id=conversation_id,
        persona_id=persona_id,
        model_id=model_id,
        provider_id=provider_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        estimated_cost=0.0,
        success=success,
        error_message=error_message
    )
    db.add(log)
    await db.commit()