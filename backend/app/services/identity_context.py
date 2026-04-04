"""Shared identity/soul/user context builder.

Used by chat, workbench, telegram bot, and any other surface where the AI
interacts with the user. Ensures consistent identity across all interactions.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"


def build_identity_context(include_method: bool = True, include_memory: bool = False) -> str:
    """Build a unified system prompt containing the AI identity and user context.

    Reads from:
      - data/soul.md       → AI personality, voice, values
      - data/user.md       → user profile, preferences, context
      - data/identity.md   → AI name, role, behavioral directives
      - Active method      → BMAD/GSD/etc system prompt (if include_method)
      - data/context/MEMORY.md → distilled long-term memory (if include_memory)

    Returns a single string ready to prepend as a system message.
    Returns empty string if no identity files exist.
    """
    parts = []

    # AI identity (soul.md)
    try:
        soul = _DATA_DIR / "soul.md"
        if soul.exists() and soul.stat().st_size > 10:
            parts.append(f"# AI Identity (Soul)\n{soul.read_text(encoding='utf-8')}")
    except Exception as e:
        logger.debug(f"Could not read soul.md: {e}")

    # Extended AI identity directives
    try:
        identity = _DATA_DIR / "identity.md"
        if identity.exists() and identity.stat().st_size > 10:
            parts.append(f"# AI Identity Directives\n{identity.read_text(encoding='utf-8')}")
    except Exception as e:
        logger.debug(f"Could not read identity.md: {e}")

    # User profile
    try:
        user = _DATA_DIR / "user.md"
        if user.exists() and user.stat().st_size > 10:
            parts.append(f"# About the User\n{user.read_text(encoding='utf-8')}")
    except Exception as e:
        logger.debug(f"Could not read user.md: {e}")

    # Active development method
    if include_method:
        try:
            from app.routes.methods import _load_state as _load_method_state, BUILT_IN_METHODS
            state = _load_method_state()
            method = BUILT_IN_METHODS.get(state.get("active_method", "standard"), {})
            method_prompt = method.get("system_prompt", "")
            if method_prompt:
                parts.append(method_prompt)
        except Exception as e:
            logger.debug(f"Could not load method prompt: {e}")

    # Long-term distilled memory
    if include_memory:
        try:
            memory = _DATA_DIR / "context" / "MEMORY.md"
            if memory.exists() and memory.stat().st_size > 10:
                content = memory.read_text(encoding='utf-8')
                # Cap at ~6KB to avoid blowing up context
                if len(content) > 6000:
                    content = content[:6000] + "\n… (truncated)"
                parts.append(f"# Long-term Memory\n{content}")
        except Exception as e:
            logger.debug(f"Could not read MEMORY.md: {e}")

    if not parts:
        return ""

    return "\n\n---\n\n".join(parts)
