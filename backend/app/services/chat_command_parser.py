"""Chat command parser -- detects system commands in user messages.

Returns a parsed command dict or None for regular chat messages.
Command format: { "action": str, "entity_type": str, "params": dict, "raw": str }

Supports:
  - Slash commands: /list-models, /add-model gpt-4, /switch-persona coder
  - Natural language: "show my models", "add model gpt-4 from openai"

This module is a pure parser -- it does NOT execute commands.
Execution is handled by downstream handlers (E11.2-E11.4).
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Slash command definitions: /command -> base template
# ---------------------------------------------------------------------------
SLASH_COMMANDS: dict[str, dict] = {
    "/list-models":    {"action": "list",   "entity_type": "model"},
    "/list-personas":  {"action": "list",   "entity_type": "persona"},
    "/list-agents":    {"action": "list",   "entity_type": "agent"},
    "/add-model":      {"action": "create", "entity_type": "model"},
    "/delete-model":   {"action": "delete", "entity_type": "model"},
    "/add-persona":    {"action": "create", "entity_type": "persona"},
    "/delete-persona": {"action": "delete", "entity_type": "persona"},
    "/switch-model":   {"action": "switch", "entity_type": "model"},
    "/switch-persona": {"action": "switch", "entity_type": "persona"},
    "/help":           {"action": "help",   "entity_type": "system"},
    "/status":         {"action": "status", "entity_type": "system"},
}

# ---------------------------------------------------------------------------
# Natural language patterns (order matters -- first match wins)
# ---------------------------------------------------------------------------
NL_PATTERNS: list[tuple[str, dict]] = [
    # ---- List -----------------------------------------------------------------
    (r"(?:show|list|display)\s+(?:my\s+)?(?:all\s+)?models",
     {"action": "list", "entity_type": "model"}),
    (r"(?:show|list|display)\s+(?:my\s+)?(?:all\s+)?personas",
     {"action": "list", "entity_type": "persona"}),
    (r"(?:show|list|display)\s+(?:my\s+)?(?:all\s+)?agents",
     {"action": "list", "entity_type": "agent"}),

    # ---- Add/Create model -----------------------------------------------------
    (r"(?:add|create|register)\s+(?:a\s+)?model\s+(?:called\s+)?['\"]?(\S+)['\"]?"
     r"\s+(?:from|using|via)\s+(\S+)",
     {"action": "create", "entity_type": "model", "param_names": ["name", "provider"]}),
    (r"(?:add|create|register)\s+(?:a\s+)?model\s+(?:called\s+)?['\"]?(\S+)['\"]?",
     {"action": "create", "entity_type": "model", "param_names": ["name"]}),

    # ---- Delete model ---------------------------------------------------------
    (r"(?:delete|remove|drop)\s+(?:the\s+)?model\s+['\"]?(\S+)['\"]?",
     {"action": "delete", "entity_type": "model", "param_names": ["name"]}),

    # ---- Create persona -------------------------------------------------------
    (r"(?:create|add|make)\s+(?:a\s+)?persona\s+(?:called|named)\s+"
     r"['\"]?(.+?)['\"]?\s+(?:that|which|who|to)\s+(.+)",
     {"action": "create", "entity_type": "persona", "param_names": ["name", "description"]}),
    (r"(?:create|add|make)\s+(?:a\s+)?persona\s+(?:called|named)\s+['\"]?(\S+)['\"]?",
     {"action": "create", "entity_type": "persona", "param_names": ["name"]}),

    # ---- Delete persona -------------------------------------------------------
    (r"(?:delete|remove|drop)\s+(?:the\s+)?persona\s+['\"]?(\S+)['\"]?",
     {"action": "delete", "entity_type": "persona", "param_names": ["name"]}),

    # ---- Switch ---------------------------------------------------------------
    (r"(?:switch|change|use)\s+(?:to\s+)?(?:the\s+)?model\s+['\"]?(\S+)['\"]?",
     {"action": "switch", "entity_type": "model", "param_names": ["name"]}),
    (r"(?:switch|change|use)\s+(?:to\s+)?(?:the\s+)?persona\s+['\"]?(\S+)['\"]?",
     {"action": "switch", "entity_type": "persona", "param_names": ["name"]}),

    # ---- Status ---------------------------------------------------------------
    (r"(?:what(?:'s| is)\s+(?:the\s+)?)?(?:system\s+)?status",
     {"action": "status", "entity_type": "system"}),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_chat_command(message: str) -> Optional[dict]:
    """Parse a user message for system commands.

    Returns:
        dict with keys ``action``, ``entity_type``, ``params``, ``raw``
        when the message is recognised as a command, or ``None`` if it is
        a regular chat message that should be forwarded to the LLM.
    """
    text = message.strip()
    if not text:
        return None

    # 1. Slash commands first (explicit mode)
    if text.startswith("/"):
        return _parse_slash_command(text)

    # 2. Natural language patterns
    return _parse_natural_language(text)


def format_command_help() -> str:
    """Return help text listing available chat commands."""
    return (
        "**Available Commands:**\n"
        "\n"
        "**Models:**\n"
        '- `/list-models` or "show my models"\n'
        '- `/add-model <name>` or "add model <name> from <provider>"\n'
        '- `/delete-model <name>` or "delete model <name>"\n'
        '- `/switch-model <name>` or "switch to model <name>"\n'
        "\n"
        "**Personas:**\n"
        '- `/list-personas` or "list personas"\n'
        '- `/add-persona <name>` or "create a persona called <name> that <description>"\n'
        '- `/delete-persona <name>` or "delete persona <name>"\n'
        '- `/switch-persona <name>` or "switch to persona <name>"\n'
        "\n"
        "**System:**\n"
        '- `/status` or "what\'s the status"\n'
        '- `/help` or "show help"\n'
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_slash_command(text: str) -> Optional[dict]:
    """Parse ``/slash-command [args]`` format."""
    parts = text.split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    template = SLASH_COMMANDS.get(cmd)
    if not template:
        return None

    result: dict = {
        "action": template["action"],
        "entity_type": template["entity_type"],
        "params": {},
        "raw": text,
    }

    # Attach arguments for commands that accept a target name
    if args and template["action"] in ("create", "delete", "switch"):
        result["params"]["name"] = args.strip().strip("'\"")

    return result


def _parse_natural_language(text: str) -> Optional[dict]:
    """Parse natural language commands using regex patterns."""
    lower = text.lower()

    for pattern, template in NL_PATTERNS:
        match = re.search(pattern, lower, re.IGNORECASE)
        if match:
            result: dict = {
                "action": template["action"],
                "entity_type": template["entity_type"],
                "params": {},
                "raw": text,
            }

            # Extract named params from capture groups
            param_names: list[str] = template.get("param_names", [])
            for i, name in enumerate(param_names):
                if i < len(match.groups()):
                    result["params"][name] = match.group(i + 1).strip().strip("'\"")

            return result

    return None
