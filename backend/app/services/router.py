"""Router service for routing requests to appropriate models."""

import time
from typing import Optional, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging
from app.models import Persona, Model, Provider
from app.services.model_client import model_client
from app.services.memory import MemoryManager, RedisUnavailableError

logger = logging.getLogger(__name__)


class ModelMeshError(Exception):
    """Base error for all ModelMesh errors."""
    def __init__(self, message: str, code: str, details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class PersonaNotFoundError(ModelMeshError):
    def __init__(self, persona_id: str):
        super().__init__(
            f"Persona not found: {persona_id}",
            "persona_not_found",
            {"persona_id": persona_id}
        )


class NoModelAvailableError(ModelMeshError):
    def __init__(self, persona_id: str):
        super().__init__(
            f"No model available for persona: {persona_id}",
            "no_model_available",
            {"persona_id": persona_id}
        )


class AllModelsFailedError(ModelMeshError):
    def __init__(self, primary: str, fallback: str, errors: list):
        super().__init__(
            "All models in failover chain failed",
            "all_models_failed",
            {"primary": primary, "fallback": fallback, "errors": [str(e) for e in errors]}
        )


class CostLimitExceededError(ModelMeshError):
    def __init__(self, estimated: float, limit: float):
        super().__init__(
            f"Estimated cost ${estimated:.4f} exceeds limit ${limit:.4f}",
            "cost_limit_exceeded",
            {"estimated_cost": estimated, "max_cost": limit}
        )


class Router:
    """Route requests to appropriate models based on persona configuration."""
    
    def __init__(self, db: AsyncSession, memory: MemoryManager):
        self.db = db
        self.memory = memory
    
    async def route_request(
        self,
        persona: Persona,
        primary_model: Model,
        fallback_model: Optional[Model],
        messages: list,
        conversation_id: Optional[str] = None,
        stream: bool = True,
        **params
    ) -> AsyncGenerator:
        """Route request to appropriate model with failover."""
        
        # 1. Build context with memory (if enabled and available)
        if persona.memory_enabled and conversation_id:
            try:
                messages = await self.memory.get_context(
                    conversation_id, messages, persona.max_memory_messages
                )
            except RedisUnavailableError:
                logger.warning("Redis unavailable, proceeding without conversation context")
        
        # 2. Check capability requirements
        required_capabilities = self._extract_required_capabilities(messages)
        if required_capabilities:
            if primary_model and not self._has_capabilities(primary_model, required_capabilities):
                primary_model = None
            if fallback_model and not self._has_capabilities(fallback_model, required_capabilities):
                fallback_model = None
        
        # 3. Check cost rules
        routing_rules = persona.routing_rules or {}
        max_cost = routing_rules.get("max_cost")
        
        if max_cost and primary_model:
            estimated_tokens = model_client.estimate_tokens(messages, primary_model)
            # Estimate output at 2x input (rough heuristic)
            estimated_cost = model_client.estimate_cost(
                estimated_tokens, estimated_tokens * 2, primary_model
            )
            
            if estimated_cost > max_cost:
                if fallback_model:
                    primary_model = fallback_model
                    fallback_model = None
                else:
                    raise CostLimitExceededError(float(estimated_cost), max_cost)
        
        # 4. Ensure we have at least one model
        if not primary_model:
            raise NoModelAvailableError(str(persona.id))
        
        # 5. Get provider
        provider = await self._get_provider(primary_model.provider_id)
        
        # 6. Try primary model, failover if needed
        try:
            # Convert messages to dict for LiteLLM
            msg_dicts = messages if isinstance(messages[0], dict) else [m.model_dump() for m in messages]
            
            async for chunk in model_client.call_model(
                primary_model, provider, msg_dicts, stream=stream, **params
            ):
                yield chunk
            
            # Store messages in memory (after successful response)
            if persona.memory_enabled and conversation_id:
                await self.memory.store_messages(
                    conversation_id, msg_dicts, persona.max_memory_messages
                )
            
        except Exception as e:
            logger.error(f"Primary model failed: {e}")
            
            if fallback_model:
                try:
                    fallback_provider = await self._get_provider(fallback_model.provider_id)
                    
                    async for chunk in model_client.call_model(
                        fallback_model, fallback_provider,
                        msg_dicts,
                        stream=stream, **params
                    ):
                        yield chunk
                    
                except Exception as fallback_error:
                    logger.error(f"Fallback model failed: {fallback_error}")
                    raise AllModelsFailedError(
                        str(primary_model.id),
                        str(fallback_model.id) if fallback_model else None,
                        [e, fallback_error]
                    )
            else:
                raise AllModelsFailedError(str(primary_model.id), None, [e])
    
    def _extract_required_capabilities(self, messages: list) -> list:
        """Extract required capabilities from messages (e.g., vision for images)."""
        capabilities = []
        for msg in messages:
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, 'content', '')
            # Check for image content (simplified)
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image":
                        capabilities.append("vision")
        return capabilities
    
    def _has_capabilities(self, model: Model, required: list) -> bool:
        """Check if model has required capabilities."""
        model_caps = model.capabilities or {}
        for cap in required:
            if not model_caps.get(cap, False):
                return False
        return True
    
    async def _get_provider(self, provider_id) -> Optional[Provider]:
        result = await self.db.execute(
            select(Provider).where(Provider.id == provider_id)
        )
        return result.scalar_one_or_none()