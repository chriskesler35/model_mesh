"""LiteLLM-based model client with unified interface."""

import os
import logging
from typing import Optional, AsyncGenerator
import litellm
from litellm import acompletion
from app.models import Model, Provider

logger = logging.getLogger(__name__)

# Drop params unsupported by specific providers (e.g. GPT-5 only accepts
# temperature=1, Anthropic ignores some OpenAI-specific fields, etc).
# Without this, calls fail with UnsupportedParamsError for any provider
# quirk. LiteLLM logs what it dropped if needed.
litellm.drop_params = True


class ModelClient:
    """LiteLLM-based model client with unified interface."""

    def get_api_key(self, provider_name: str) -> Optional[str]:
        """Get API key from environment (never from database)."""
        p = provider_name.lower()
        if p == "google":
            # litellm Gemini handler requires explicit api_key; prefer GEMINI_API_KEY
            return (os.environ.get("GEMINI_API_KEY")
                    or os.environ.get("GOOGLE_API_KEY"))
        key_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "openai-codex": "OPENAI_API_KEY",  # Codex endpoint, same key as regular OpenAI
            "openrouter": "OPENROUTER_API_KEY",
        }
        env_key = key_map.get(p)
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
        import os

        provider_name = provider.name.lower()

        # LiteLLM format varies by provider:
        # - Anthropic: "claude-sonnet-4-6" (uses ANTHROPIC_API_KEY)
        # - Google: "gemini/gemini-2.5-pro" (uses GOOGLE_API_KEY or GEMINI_API_KEY)
        # - Ollama: "ollama/llama3" (uses api_base)
        # - OpenRouter: "openrouter/anthropic/claude-sonnet-4" (uses OPENROUTER_API_KEY)

        if provider_name == "anthropic":
            litellm_model = model.model_id
        elif provider_name == "google":
            litellm_model = f"gemini/{model.model_id}"
        elif provider_name == "openrouter":
            litellm_model = f"openrouter/{model.model_id}"
        else:
            litellm_model = f"{provider_name}/{model.model_id}"

        # Build kwargs
        kwargs = {
            "model": litellm_model,
            "messages": messages,
            "stream": stream,
            **params
        }

        # Add provider-specific config
        if provider_name == "ollama":
            # Use environment variable for Ollama URL (works in Docker)
            ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            kwargs["api_base"] = ollama_base
        elif provider_name == "google":
            # DO NOT set api_base for Google/Gemini — litellm handles the URL
            # automatically when api_key is provided. Setting api_base causes
            # litellm to route to Vertex AI instead of Google AI Studio.
            pass
        elif provider.api_base_url and provider_name not in ("anthropic",):
            kwargs["api_base"] = provider.api_base_url

        # Get API key from environment (provider-specific)
        api_key = self.get_api_key(provider.name)
        if api_key:
            kwargs["api_key"] = api_key

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        _key_hint = kwargs.get('api_key', '')[:8] if kwargs.get('api_key') else 'MISSING'
        logger.info(f"Calling model: {litellm_model} | stream={stream} | api_key={_key_hint} | provider={provider_name}")

        # Use acompletion for async support
        response = await acompletion(**kwargs)

        if stream:
            return self._stream_response(response)
        else:
            return response

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