"""LiteLLM-based model client with unified interface."""

import os
import logging
import uuid
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


# Real model IDs that the Copilot/Codex API exposes directly.
# These must NOT be remapped — they are distinct live models, not aliases.
_REAL_VERSIONED_MODEL_IDS: frozenset[str] = frozenset({
    "gpt-5.2",
    "gpt-5.2-codex",
    "gpt-5.3-codex",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.5",
    "gpt-5.5-pro",
})


def _normalize_codex_model_id(model_id: str) -> str:
    """Map legacy/alias Codex model IDs to provider-canonical IDs.

    Some stored rows or older templates still reference aliases such as
    `gpt-5-codex`, while current OpenAI/Codex catalogs expose `gpt-5`.
    Never remaps real versioned model IDs (e.g. gpt-5.5) that are exposed
    directly by the GitHub Copilot or Codex APIs.
    """
    normalized = (model_id or "").strip().lower()
    # Never remap real versioned model IDs — they are not aliases.
    if normalized in _REAL_VERSIONED_MODEL_IDS:
        return model_id
    alias_map = {
        "gpt-5-codex": "gpt-5",
    }
    mapped = alias_map.get(normalized)
    if mapped:
        return mapped
    return model_id

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
        raw_model_id = model.model_id or ""
        raw_model_id_lower = raw_model_id.lower()
        # GitHub Copilot exposes real versioned model IDs directly; never remap them.
        effective_model_id = raw_model_id if provider_name == "github-copilot" else _normalize_codex_model_id(raw_model_id)
        model_id_lower = effective_model_id.lower()
        # Treat all gpt-5 variants (gpt-5, gpt-5-mini, gpt-5.x, gpt-5.x-*) as
        # Codex-family so they route through the OAuth proxy when available.
        _is_gpt5_variant = raw_model_id_lower.startswith("gpt-5") or model_id_lower.startswith("gpt-5")
        is_codex_family_model = ("codex" in raw_model_id_lower) or ("codex" in model_id_lower) or _is_gpt5_variant
        is_openai_provider = provider_name in ("openai", "openai-codex")
        api_key = self.get_api_key(provider.name)
        use_codex_proxy = should_use_codex_oauth_proxy(provider_name, api_key=api_key)

        # If a codex-family model is registered under the plain OpenAI provider,
        # still route via the OAuth proxy path when available. This keeps
        # gpt-*-codex behavior consistent with OAuth-only setups.
        if is_openai_provider and is_codex_family_model and not use_codex_proxy:
            use_codex_proxy = should_use_codex_oauth_proxy("openai-codex", api_key=api_key)

        # LiteLLM format varies by provider:
        # - Anthropic: "claude-sonnet-4-6" (uses ANTHROPIC_API_KEY)
        # - Google: "gemini/gemini-2.5-pro" (uses GOOGLE_API_KEY or GEMINI_API_KEY)
        # - Ollama: "ollama/llama3" (uses api_base)
        # - OpenRouter: "openrouter/anthropic/claude-sonnet-4" (uses OPENROUTER_API_KEY)

        if provider_name == "anthropic":
            litellm_model = effective_model_id
        elif provider_name == "google":
            litellm_model = f"gemini/{effective_model_id}"
        elif provider_name == "openrouter":
            litellm_model = f"openrouter/{effective_model_id}"
        elif provider_name == "openai-codex" or (is_openai_provider and is_codex_family_model):
            # The dedicated Codex provider uses OpenAI-compatible model names,
            # but the actual transport can be the local OAuth proxy.
            litellm_model = f"openai/{effective_model_id}"
        elif provider_name == "github-copilot":
            # GitHub Copilot has an OpenAI-compatible endpoint but requires
            # a special Copilot token exchanged from a GitHub OAuth token.
            # Route through LiteLLM's openai/ prefix and override api_base
            # + api_key below.
            litellm_model = f"openai/{effective_model_id}"
        else:
            litellm_model = f"{provider_name}/{effective_model_id}"

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
            if codex_proxy_rejects_temperature(effective_model_id):
                kwargs.pop("temperature", None)
        elif is_openai_provider and is_codex_family_model:
            # Codex-family models are expected to run through OAuth proxy mode.
            # If we are here, the proxy path was not selected/reachable.
            proxy_base = get_codex_proxy_base_url()
            configuration_issue = get_codex_proxy_configuration_issue()
            if configuration_issue:
                raise ValueError(
                    f"Codex OAuth routing is required for model '{raw_model_id}', but proxy configuration is invalid. "
                    f"{configuration_issue}"
                )
            if not is_codex_proxy_reachable(cache_ttl_seconds=0):
                raise ValueError(
                    f"Codex OAuth proxy is offline at {proxy_base}. "
                    "Start the Codex OAuth HTTP proxy and retry."
                )
            kwargs["api_base"] = proxy_base
            kwargs.pop("temperature", None)
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
        elif provider_name == "openai-codex" or (is_openai_provider and is_codex_family_model):
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
        if raw_model_id != effective_model_id:
            logger.info(f"Codex model alias normalized: {raw_model_id} -> {effective_model_id}")
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


    async def call_model_with_tools(
        self,
        model: Model,
        provider: Provider,
        messages: list,
        tools: list,
        **params,
    ) -> tuple:
        """Call a model with OpenAI-format tool definitions.

        Uses ``stream=False`` because accumulating tool-call argument fragments
        from a streaming response is fragile and unnecessary for the agent loop.

        Returns:
            (response_text, tool_calls, input_tokens, output_tokens)

        Where ``tool_calls`` is a list of dicts::

            [{"id": str, "name": str, "arguments": dict}, ...]

        An empty list means the model responded with plain text and no tool use.
        """
        import json as _json

        # Reuse all existing provider/key/routing logic via call_model().
        # tools= and tool_choice= flow through **params → acompletion(**kwargs).
        response = await self.call_model(
            model=model,
            provider=provider,
            messages=messages,
            stream=False,
            tools=tools,
            tool_choice="auto",
            **params,
        )

        response_text = ""
        tool_calls: list[dict] = []
        input_tokens = 0
        output_tokens = 0

        try:
            choice = response.choices[0]
            msg = choice.message
            response_text = msg.content or ""

            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    raw_args = tc.function.arguments if hasattr(tc.function, "arguments") else {}
                    args = {}

                    if isinstance(raw_args, dict):
                        args = raw_args
                    elif isinstance(raw_args, str):
                        candidate = raw_args.strip()
                        for _ in range(3):
                            try:
                                decoded = _json.loads(candidate)
                            except (ValueError, TypeError):
                                break

                            if isinstance(decoded, dict):
                                args = decoded
                                break
                            if isinstance(decoded, str):
                                candidate = decoded.strip()
                                continue
                            break

                        if not args and isinstance(candidate, str):
                            # Best-effort fallback for common backslash-escaped payloads.
                            unescaped = candidate.replace('\\"', '"')
                            try:
                                decoded = _json.loads(unescaped)
                                if isinstance(decoded, dict):
                                    args = decoded
                            except (ValueError, TypeError):
                                pass

                    tool_calls.append(
                        {
                            "id": getattr(tc, "id", "") or f"call_{uuid.uuid4().hex[:8]}",
                            "name": tc.function.name,
                            "arguments": args,
                        }
                    )
        except Exception as exc:
            logger.warning("Failed to parse tool-call response: %s", exc)

        try:
            if hasattr(response, "usage") and response.usage:
                input_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(response.usage, "completion_tokens", 0) or 0
        except Exception:
            pass

        return response_text, tool_calls, input_tokens, output_tokens


model_client = ModelClient()
