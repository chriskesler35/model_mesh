"""Chat command parser -- detects actionable commands in natural language chat messages.

Parses user messages like "add model gpt-4 from openai", "list my models",
"delete model X", "switch to model Y" and returns structured command dicts
for the dispatcher to execute.

Returns:
    None if the message is not a command.
    dict with {action, entity_type, params} if a command is detected.
"""

from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Model command patterns ────────────────────────────────────────────────────
# Each tuple: (compiled_regex, action, param_extractor_lambda)

_MODEL_PATTERNS: list[tuple[re.Pattern, str, callable]] = []


def _mp(pattern: str, action: str, extractor):
    """Register a model command pattern."""
    _MODEL_PATTERNS.append((re.compile(pattern, re.IGNORECASE), action, extractor))


# "add model <name> from <provider>"
_mp(
    r"^(?:add|create|register|new)\s+model\s+([^\s]+)(?:\s+(?:from|on|via|provider)\s+(.+))?$",
    "create",
    lambda m: {"name": m.group(1).strip(), "provider": (m.group(2) or "").strip()},
)

# "remove/delete model <name>"
_mp(
    r"^(?:remove|delete|deactivate|disable)\s+model\s+(.+)$",
    "delete",
    lambda m: {"name": m.group(1).strip()},
)

# "list models" / "list my models" / "show models"
_mp(
    r"^(?:list|show|get|display)\s+(?:my\s+)?models?$",
    "list",
    lambda m: {},
)

# "switch to model <name>" / "use model <name>" / "set model <name> as default"
_mp(
    r"^(?:switch\s+(?:to\s+)?|use\s+|set\s+)model\s+([^\s]+)(?:\s+as\s+default(?:\s+for\s+(.+))?)?$",
    "switch",
    lambda m: {"name": m.group(1).strip(), "purpose": (m.group(2) or "").strip()},
)

# Slash-command variants: /add-model, /list-models, /delete-model
_mp(
    r"^/add[-_]?model\s+([^\s]+)(?:\s+(?:from|on|via)\s+(.+))?$",
    "create",
    lambda m: {"name": m.group(1).strip(), "provider": (m.group(2) or "").strip()},
)
_mp(
    r"^/(?:list|show)[-_]?models?$",
    "list",
    lambda m: {},
)
_mp(
    r"^/(?:delete|remove)[-_]?model\s+(.+)$",
    "delete",
    lambda m: {"name": m.group(1).strip()},
)

# ── System command patterns ───────────────────────────────────────────────────
_SYSTEM_PATTERNS: list[tuple[re.Pattern, str, callable]] = []


def _sp(pattern: str, action: str, extractor):
    """Register a system command pattern."""
    _SYSTEM_PATTERNS.append((re.compile(pattern, re.IGNORECASE), action, extractor))


_sp(r"^/?help$", "help", lambda m: {})
_sp(r"^/?status$", "status", lambda m: {})


# ── Public API ────────────────────────────────────────────────────────────────

def parse_chat_command(message: str) -> Optional[dict]:
    """Parse a user chat message into a structured command.

    Args:
        message: Raw user message text.

    Returns:
        None if the message is not a recognized command.
        dict with keys:
            - action: str (create, delete, list, switch, help, status)
            - entity_type: str (model, system)
            - params: dict (action-specific parameters)
    """
    text = (message or "").strip()
    if not text:
        return None

    # Try model patterns first
    for pattern, action, extractor in _MODEL_PATTERNS:
        match = pattern.match(text)
        if match:
            params = extractor(match)
            logger.info(f"Parsed model command: action={action}, params={params}")
            return {"action": action, "entity_type": "model", "params": params}

    # Try system patterns
    for pattern, action, extractor in _SYSTEM_PATTERNS:
        match = pattern.match(text)
        if match:
            params = extractor(match)
            return {"action": action, "entity_type": "system", "params": params}

    return None


def format_command_help() -> str:
    """Return help text listing available chat commands."""
    return """**Available Chat Commands:**

| Command | Description |
|---------|-------------|
| `add model <name> from <provider>` | Add a new model |
| `list models` | Show all active models |
| `delete model <name>` | Deactivate a model |
| `switch to model <name>` | Get info on using a model |
| `/help` | Show this help |
| `/status` | System status |

**Examples:**
- "add model gemini-2.5-pro from google"
- "list my models"
- "remove model gpt-3.5-turbo"
- "switch to model claude-sonnet"
"""
