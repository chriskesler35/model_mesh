"""Router service for routing requests to appropriate models."""

import time
from typing import Optional, AsyncGenerator, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging
from app.models import Persona, Model, Provider
from app.services.model_client import model_client
from app.services.memory import MemoryManager, RedisUnavailableError

logger = logging.getLogger(__name__)

# Classification categories and their routing hints
CLASSIFICATION_ROUTES = {
    "CODE": {"prefer_reasoning": True, "suggest_models": ["claude-sonnet", "claude-opus", "gpt-4"]},
    "MATH": {"prefer_reasoning": True, "suggest_models": ["claude-sonnet", "gpt-4", "gemini-pro"]},
    "CREATIVE": {"prefer_reasoning": False, "suggest_models": ["claude-sonnet", "gpt-4", "gemini-flash"]},
    "SIMPLE": {"prefer_reasoning": False, "suggest_models": ["llama", "gemini-flash", "local"]},
    "ANALYSIS": {"prefer_reasoning": True, "suggest_models": ["claude-sonnet", "gpt-4"]},
}

CLASSIFIER_PROMPT = """Classify this request into ONE category. Reply with ONLY the category name, nothing else.

Categories: CODE, MATH, CREATIVE, SIMPLE, ANALYSIS

Request: {prompt}

Category:"""


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

    async def classify_request(self, messages: list, classifier_persona: Persona = None) -> str:
        """
        Classify a request using a fast local model.
        Returns category: CODE, MATH, CREATIVE, SIMPLE, or ANALYSIS.
        """
        # Get the first user message for classification
        prompt = ""
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                prompt = msg.get("content", "")[:500]  # Truncate for speed
                break

        if not prompt:
            return "SIMPLE"

        # If no classifier persona, use simple heuristics
        if not classifier_persona:
            return self._heuristic_classify(prompt)

        try:
            # Use the classifier persona's model for classification
            # This should be a fast/cheap local model
            classifier_model = await self._get_model(classifier_persona.primary_model_id)
            classifier_provider = await self._get_provider(classifier_model.provider_id)

            classify_prompt = CLASSIFIER_PROMPT.format(prompt=prompt)

            response = await model_client.call_model(
                classifier_model,
                classifier_provider,
                [{"role": "user", "content": classify_prompt}],
                stream=False,
                max_tokens=10,
                temperature=0.1
            )

            # Extract classification from response
            if hasattr(response, 'choices') and response.choices:
                classification = response.choices[0].message.content.strip().upper()

                # Validate it's a known category
                if classification in CLASSIFICATION_ROUTES:
                    logger.info(f"Classified request as: {classification}")
                    return classification

            # Fallback to heuristic if model returns garbage
            return self._heuristic_classify(prompt)

        except Exception as e:
            logger.warning(f"Classification failed, using heuristic: {e}")
            return self._heuristic_classify(prompt)

    def _heuristic_classify(self, prompt: str) -> str:
        """Simple heuristic classification when model unavailable."""
        prompt_lower = prompt.lower()

        code_keywords = ["function", "code", "implement", "debug", "error", "variable", "class", "method", "api", "script"]
        math_keywords = ["calculate", "formula", "equation", "solve", "math", "number", "sum", "average", "percentage"]
        creative_keywords = ["write", "story", "creative", "poem", "imagine", "narrative", "blog", "article"]
        analysis_keywords = ["analyze", "compare", "review", "evaluate", "assess", "explain", "why", "how does"]

        # Count keyword matches
        code_score = sum(1 for kw in code_keywords if kw in prompt_lower)
        math_score = sum(1 for kw in math_keywords if kw in prompt_lower)
        creative_score = sum(1 for kw in creative_keywords if kw in prompt_lower)
        analysis_score = sum(1 for kw in analysis_keywords if kw in prompt_lower)

        scores = {
            "CODE": code_score,
            "MATH": math_score,
            "CREATIVE": creative_score,
            "ANALYSIS": analysis_score,
        }

        max_score = max(scores.values())

        # If no keywords match or score is low, classify as SIMPLE
        if max_score == 0 or max_score < 2:
            return "SIMPLE"

        # Return highest scoring category
        for category, score in scores.items():
            if score == max_score:
                return category

        return "SIMPLE"

    async def route_request(
        self,
        persona: Persona,
        primary_model: Model,
        fallback_model: Optional[Model],
        messages: list,
        conversation_id: Optional[str] = None,
        stream: bool = True,
        **params
    ) -> Union[AsyncGenerator, dict]:
        """Route request to appropriate model with failover."""

        # 1. Build context with memory (if enabled and available)
        if persona.memory_enabled and conversation_id:
            try:
                messages = await self.memory.get_context(
                    conversation_id, messages, persona.max_memory_messages
                )
            except RedisUnavailableError:
                logger.warning("Redis unavailable, proceeding without conversation context")

        # 2. Auto-routing: classify and potentially switch models
        routing_rules = persona.routing_rules or {}
        if routing_rules.get("auto_route") and routing_rules.get("classifier_persona_id"):
            try:
                # Get classifier persona
                classifier_persona = await self._get_persona(routing_rules["classifier_persona_id"])

                # Classify the request
                category = await self.classify_request(messages, classifier_persona)
                route_hint = CLASSIFICATION_ROUTES.get(category, {})

                # Log the routing decision
                logger.info(f"Auto-routing: {category} -> {route_hint.get('suggest_models', [])}")

                # Could optionally switch models based on category here
                # For now, we just log the classification

            except Exception as e:
                logger.warning(f"Auto-routing failed, continuing with default: {e}")

        # 3. Check capability requirements
        required_capabilities = self._extract_required_capabilities(messages)
        if required_capabilities:
            if primary_model and not self._has_capabilities(primary_model, required_capabilities):
                primary_model = None
            if fallback_model and not self._has_capabilities(fallback_model, required_capabilities):
                fallback_model = None

        # 4. Check cost rules
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

        # 5. Ensure we have at least one model
        if not primary_model:
            raise NoModelAvailableError(str(persona.id))

        # 6. Get provider
        provider = await self._get_provider(primary_model.provider_id)

        # 7. Convert messages to dict for LiteLLM
        msg_dicts = messages if isinstance(messages[0], dict) else [m.model_dump() for m in messages]

        # 8. Try primary model, failover if needed
        try:
            if stream:
                # For streaming, return async generator
                async def stream_generator():
                    async for chunk in await model_client.call_model(
                        primary_model, provider, msg_dicts, stream=True, **params
                    ):
                        yield chunk

                    # Store messages in memory after successful response
                    if persona.memory_enabled and conversation_id:
                        await self.memory.store_messages(
                            conversation_id, msg_dicts, persona.max_memory_messages
                        )

                return stream_generator()
            else:
                # For non-streaming, await the response
                response = await model_client.call_model(
                    primary_model, provider, msg_dicts, stream=False, **params
                )

                # Store messages in memory after successful response
                if persona.memory_enabled and conversation_id:
                    await self.memory.store_messages(
                        conversation_id, msg_dicts, persona.max_memory_messages
                    )

                return response

        except Exception as e:
            logger.error(f"Primary model failed: {e}")

            if fallback_model:
                try:
                    fallback_provider = await self._get_provider(fallback_model.provider_id)

                    if stream:
                        async def fallback_stream_generator():
                            async for chunk in await model_client.call_model(
                                fallback_model, fallback_provider, msg_dicts, stream=True, **params
                            ):
                                yield chunk

                            if persona.memory_enabled and conversation_id:
                                await self.memory.store_messages(
                                    conversation_id, msg_dicts, persona.max_memory_messages
                                )

                        return fallback_stream_generator()
                    else:
                        response = await model_client.call_model(
                            fallback_model, fallback_provider, msg_dicts, stream=False, **params
                        )

                        if persona.memory_enabled and conversation_id:
                            await self.memory.store_messages(
                                conversation_id, msg_dicts, persona.max_memory_messages
                            )

                        return response

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

    async def _get_model(self, model_id) -> Optional[Model]:
        result = await self.db.execute(
            select(Model).where(Model.id == model_id)
        )
        return result.scalar_one_or_none()

    async def _get_persona(self, persona_id: str) -> Optional[Persona]:
        result = await self.db.execute(
            select(Persona).where(Persona.id == persona_id)
        )
        return result.scalar_one_or_none()