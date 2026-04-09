"""Dispatch parsed chat commands to the appropriate executor.

This module acts as the routing layer between the chat command parser
and the individual command executors (model_commands, etc.).
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def dispatch_command(
    command: dict,
    db: AsyncSession,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Route a parsed command to the appropriate executor.

    Args:
        command: Parsed command dict from chat_command_parser.
        db: Async database session.
        conversation_id: Optional conversation ID for audit logging.

    Returns:
        Formatted response string for the chat UI.
    """
    entity_type = command.get("entity_type", "")

    if entity_type == "model":
        from app.services.chat_commands.model_commands import execute_model_command
        return await execute_model_command(
            command, db, conversation_id=conversation_id
        )

    elif entity_type == "system":
        return await _handle_system_command(command)

    logger.warning(f"Unhandled command entity_type: {entity_type}")
    return f"Command type '{entity_type}' is not yet supported."


async def _handle_system_command(command: dict) -> str:
    """Handle system-level commands (help, status)."""
    action = command.get("action", "")

    if action == "help":
        from app.services.chat_command_parser import format_command_help
        return format_command_help()

    elif action == "status":
        return (
            "System is running. "
            "Use 'list models' to see configured models, "
            "or type 'help' for available commands."
        )

    return f"Unknown system command: {action}"
