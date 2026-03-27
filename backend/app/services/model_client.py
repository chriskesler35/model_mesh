"""LiteLLM-based model client with unified interface."""

import os
import time
from typing import Optional, AsyncGenerator
import logging
from litellm import acompletion
from app.config import settings
from app.models import Model, Provider

logger = logging.getLogger(__name__)


class ModelClient:
    """LiteLLM-based model client with unified interface."""
    
    def get_api_key(self, provider_name: str) -> Optional[str]:
        """Get API key from environment (never from database)."""
        key_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "openai": "OPENAI_API_KEY",
        }
        env_key = key_map.get(provider_name.lower())
        if env_key:
            return os.environ.get(env_key)
        return None
    
    async def call_model(
        self,
        model: Model,
        provider: Provider,
        messages: list,
        stream: bool = True,
        **params
    ):
        """Call model via LiteLLM with unified interface."""
        # LiteLLM format: "provider/model_name"
        litellm_model = f"{provider.name}/{model.model_id}"
        
        # Get API key from environment
        api_key = self.get_api_key(provider.name) if provider.auth_type == "api_key" else None
        
        # Build kwargs
        kwargs = {
            "model": litellm_model,
            "messages": messages,
            "stream": stream,
            **params
        }
        
        # Add provider-specific config
        if provider.api_base_url:
            kwargs["api_base"] = provider.api_base_url
        
        if api_key:
            kwargs["api_key"] = api_key
        
        # Use acompletion for async support
        response = await acompletion(**kwargs)
        
        if stream:
            return self._stream_response(response)
        else:
            return await response
    
    async def _stream_response(self, response) -> AsyncGenerator:
        """Yield streaming chunks."""
        async for chunk in response:
            yield chunk
    
    def estimate_tokens(self, messages: list, model: Model) -> int:
        """Estimate token count for messages."""
        import tiktoken
        
        # Use cl100k_base encoding (good for most models)
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")
        
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(encoding.encode(content))
            # Add overhead for role, etc.
            total += 4
        
        return total
    
    def estimate_cost(
        self, input_tokens: int, output_tokens: int, model: Model
    ) -> float:
        """Calculate estimated cost in USD."""
        input_cost = (input_tokens / 1_000_000) * float(model.cost_per_1m_input)
        output_cost = (output_tokens / 1_000_000) * float(model.cost_per_1m_output)
        return input_cost + output_cost


model_client = ModelClient()