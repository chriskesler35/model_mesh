"""LiteLLM-based model client with unified interface."""

import os
import logging
from typing import Optional, AsyncGenerator
import litellm
from litellm import acompletion
from app.models import Model, Provider
from app.services.codex_oauth import (
    codex_proxy_rejects_temperature,
    get_codex_proxy_api_key,
    get_codex_proxy_base_url,
    get_codex_proxy_configuration_issue,
    is_codex_proxy_reachable,
    should_use_codex_oauth_proxy,
)
from app.services.provider_credentials import get_provider_api_key

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
        return get_provider_api_key(provider_name)

    async def call_model(
        self,
        model: Model,
        provider: Provider,
        messages: list,
        stream: bool = True,
        **params
    ):
        """Call model via LiteLLM with unified interface."""
        provider_name = provider.name.lower()
        api_key = self.get_api_key(provider.name)
        use_codex_proxy = should_use_codex_oauth_proxy(provider_name, api_key=api_key)

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
        elif provider_name == "openai-codex":
            # The dedicated Codex provider uses OpenAI-compatible model names,
            # but the actual transport can be the local OAuth proxy.
            litellm_model = f"openai/{model.model_id}"
        elif provider_name == "github-copilot":
            # GitHub Copilot has an OpenAI-compatible endpoint but requires
            # a special Copilot token exchanged from a GitHub OAuth token.
            # Route through LiteLLM's openai/ prefix and override api_base
            # + api_key below.
            litellm_model = f"openai/{model.model_id}"
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
        elif use_codex_proxy:
            kwargs["api_base"] = get_codex_proxy_base_url()
            if codex_proxy_rejects_temperature(model.model_id):
                kwargs.pop("temperature", None)
        elif provider_name == "openai-codex":
            # The provider record is synced with the local Codex proxy base URL,
            # but when we are not actively routing through that proxy we must
            # fall back to the standard OpenAI-compatible endpoint.
            kwargs["api_base"] = "https://api.openai.com/v1"
        elif provider_name == "github-copilot":
            # Copilot accepts the stored GitHub OAuth token directly.
            from app.services.command_executor import get_first_github_token
            from app.services.github_copilot import (
                exchange_for_copilot_token, get_copilot_headers, COPILOT_API_BASE,
            )
            gh_token = get_first_github_token()
            copilot_token = await exchange_for_copilot_token(gh_token) if gh_token else None
            if not copilot_token:
                raise ValueError(
                    "GitHub Copilot is not available. Sign in with GitHub first "
                    "(and ensure your account has a Copilot subscription)."
                )
            kwargs["api_base"] = COPILOT_API_BASE
            kwargs["api_key"] = copilot_token
            # Add Copilot-specific headers
            kwargs["extra_headers"] = get_copilot_headers()
        elif provider.api_base_url and provider_name not in ("anthropic",):
            kwargs["api_base"] = provider.api_base_url

        # Get API key from environment (provider-specific). When we are routing
        # through the local OAuth proxy, the proxy injects the bearer token.
        if use_codex_proxy:
            kwargs["api_key"] = get_codex_proxy_api_key()
        elif provider_name == "github-copilot":
            pass  # api_key already set above
        elif api_key:
            kwargs["api_key"] = api_key
        elif provider_name == "openai-codex":
            proxy_base = get_codex_proxy_base_url()
            configuration_issue = get_codex_proxy_configuration_issue()
            if configuration_issue:
                raise ValueError(
                    f"OpenAI Codex is not usable right now. {configuration_issue} "
                    "Configure CODEX_OAUTH_PROXY_BASE_URL to a compatible HTTP proxy or set OPENAI_API_KEY."
                )
            if not is_codex_proxy_reachable():
                raise ValueError(
                    f"OpenAI Codex proxy is offline at {proxy_base}. "
                    "Configure an OpenAI-compatible HTTP proxy at CODEX_OAUTH_PROXY_BASE_URL, "
                    "set OPENAI_API_KEY, or choose a different model."
                )
            raise ValueError(
                "OpenAI Codex does not have live credentials right now. "
                "Reconnect Codex OAuth or choose a different model."
            )

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
