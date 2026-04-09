"""Execute persona management commands from chat.

Handles parsed commands with entity_type="persona" and routes to the
appropriate CRUD operation (create, update, switch, show).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona import Persona
from app.models.model import Model
from app.models.conversation import Conversation
from app.models.user_profile import SystemModification

logger = logging.getLogger(__name__)


async def execute_persona_command(
    command: dict,
    db: AsyncSession,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Execute a persona-related chat command and return a response string."""
    action = command["action"]
    params = command.get("params", {})

    handlers = {
        "create": _create_persona,
        "update": _update_persona,
        "switch": _switch_persona,
        "show": _show_persona,
        "list": _list_personas,
    }

    handler = handlers.get(action)
    if not handler:
        return f"Unknown persona action: {action}"

    return await handler(db, params, conversation_id=conversation_id)


# ── Create persona ────────────────────────────────────────────────────────────

async def _create_persona(
    db: AsyncSession,
    params: dict,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Create a new persona from chat command parameters."""
    name = params.get("name", "").strip()
    if not name:
        return "Please specify a persona name. Example: \"create a persona called 'SQL Expert'\""

    # Check if name already exists
    existing = await db.execute(
        select(Persona).where(Persona.name == name)
    )
    if existing.scalar_one_or_none():
        return f"A persona named **{name}** already exists. Use 'update persona {name}' to modify it."

    description = params.get("description", "").strip()
    model_name = params.get("model", "").strip()

    # Generate system prompt from description if provided
    system_prompt = description if description else f"You are {name}."

    # Resolve model if specified
    primary_model_id = None
    model_display = None
    if model_name:
        model_obj = await _fuzzy_find_model(db, model_name)
        if model_obj:
            primary_model_id = model_obj.id
            model_display = model_obj.display_name or model_obj.model_id
        else:
            return f"Model '{model_name}' not found. Use 'list models' to see available models."

    new_persona = Persona(
        name=name,
        description=description or f"{name} persona",
        system_prompt=system_prompt,
        primary_model_id=primary_model_id,
        memory_enabled=True,
        max_memory_messages=10,
        is_default=False,
        updated_at=datetime.utcnow(),
    )
    db.add(new_persona)
    await db.commit()
    await db.refresh(new_persona)

    await _log_modification(
        db,
        modification_type="create_persona",
        entity_type="persona",
        entity_id=new_persona.id,
        before_value=None,
        after_value={"name": name, "model": model_display},
        reason="Created via chat command",
        conversation_id=conversation_id,
    )

    parts = [f"Persona **{name}** created."]
    if model_display:
        parts.append(f"Model: {model_display}")
    if description:
        parts.append(f"System prompt: \"{system_prompt}\"")
    parts.append("Use 'switch to persona " + name + "' to activate it.")
    return " ".join(parts)


# ── Update persona ────────────────────────────────────────────────────────────

async def _update_persona(
    db: AsyncSession,
    params: dict,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Update an existing persona."""
    name = params.get("name", "").strip()
    if not name:
        return "Please specify which persona to update. Example: 'update persona SQL Expert to use claude-sonnet'"

    persona = await _find_persona_by_name(db, name)
    if not persona:
        return f"Persona '{name}' not found. Use 'list personas' to see available personas."

    before = {
        "model_id": str(persona.primary_model_id) if persona.primary_model_id else None,
        "system_prompt": persona.system_prompt,
        "description": persona.description,
    }

    changes = []

    # Update model if specified
    model_name = params.get("model", "").strip()
    if model_name:
        model_obj = await _fuzzy_find_model(db, model_name)
        if model_obj:
            persona.primary_model_id = model_obj.id
            changes.append(f"model → **{model_obj.display_name or model_obj.model_id}**")
        else:
            return f"Model '{model_name}' not found. Use 'list models' to see available models."

    # Update description / system prompt if specified
    description = params.get("description", "").strip()
    if description:
        persona.description = description
        persona.system_prompt = description
        changes.append(f"system prompt updated")

    if not changes:
        return f"Nothing to update. Specify a model or description. Example: 'update persona {name} to use claude-sonnet'"

    persona.updated_at = datetime.utcnow()
    await db.commit()

    await _log_modification(
        db,
        modification_type="update_persona",
        entity_type="persona",
        entity_id=persona.id,
        before_value=before,
        after_value={
            "model_id": str(persona.primary_model_id) if persona.primary_model_id else None,
            "system_prompt": persona.system_prompt,
        },
        reason="Updated via chat command",
        conversation_id=conversation_id,
    )

    return f"Persona **{persona.name}** updated: {', '.join(changes)}."


# ── Switch persona ────────────────────────────────────────────────────────────

async def _switch_persona(
    db: AsyncSession,
    params: dict,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Switch the active persona for the current conversation."""
    name = params.get("name", "").strip()
    if not name:
        return "Please specify which persona to switch to. Example: 'switch to persona SQL Expert'"

    persona = await _find_persona_by_name(db, name)
    if not persona:
        return f"Persona '{name}' not found. Use 'list personas' to see available personas."

    # Update conversation's persona_id if we have a conversation
    if conversation_id:
        try:
            conv_uuid = uuid.UUID(conversation_id)
            conv = await db.get(Conversation, conv_uuid)
            if conv:
                conv.persona_id = persona.id
                await db.commit()
        except (ValueError, Exception) as e:
            logger.warning(f"Could not update conversation persona: {e}")

    model_info = ""
    if persona.primary_model:
        model_info = f" (model: {persona.primary_model.display_name or persona.primary_model.model_id})"

    return f"Switched to persona **{persona.name}**{model_info}. All messages in this conversation will now use this persona."


# ── Show persona ──────────────────────────────────────────────────────────────

async def _show_persona(
    db: AsyncSession,
    params: dict,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Display persona configuration details."""
    name = params.get("name", "").strip()
    if not name:
        return "Please specify which persona to show. Example: 'show persona SQL Expert'"

    persona = await _find_persona_by_name(db, name)
    if not persona:
        return f"Persona '{name}' not found. Use 'list personas' to see available personas."

    # Eagerly load model relationships
    if persona.primary_model_id:
        model_result = await db.execute(
            select(Model).where(Model.id == persona.primary_model_id)
        )
        primary = model_result.scalar_one_or_none()
    else:
        primary = None

    fallback = None
    if persona.fallback_model_id:
        fb_result = await db.execute(
            select(Model).where(Model.id == persona.fallback_model_id)
        )
        fallback = fb_result.scalar_one_or_none()

    lines = [
        f"**Persona: {persona.name}**\n",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Description | {persona.description or '—'} |",
        f"| System Prompt | {(persona.system_prompt or '—')[:100]}{'…' if persona.system_prompt and len(persona.system_prompt) > 100 else ''} |",
        f"| Primary Model | {(primary.display_name or primary.model_id) if primary else '—'} |",
        f"| Fallback Model | {(fallback.display_name or fallback.model_id) if fallback else '—'} |",
        f"| Memory Enabled | {'Yes' if persona.memory_enabled else 'No'} |",
        f"| Max Memory | {persona.max_memory_messages} messages |",
        f"| Default | {'Yes' if persona.is_default else 'No'} |",
    ]

    return "\n".join(lines)


# ── List personas ─────────────────────────────────────────────────────────────

async def _list_personas(
    db: AsyncSession,
    params: dict,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """List all personas as a formatted markdown table."""
    result = await db.execute(
        select(Persona).order_by(Persona.name)
    )
    personas = result.scalars().all()

    if not personas:
        return "No personas configured. Use 'create persona <name>' to add one."

    lines = ["**Your Personas:**\n"]
    lines.append("| Persona | Description | Default |")
    lines.append("|---------|-------------|---------|")

    for p in personas:
        desc = (p.description or "—")[:50]
        default = "✓" if p.is_default else ""
        lines.append(f"| {p.name} | {desc} | {default} |")

    lines.append(f"\n*{len(personas)} persona(s) configured*")
    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _find_persona_by_name(db: AsyncSession, name: str) -> Optional[Persona]:
    """Find a persona by exact or case-insensitive name match."""
    result = await db.execute(
        select(Persona).where(Persona.name.ilike(name))
    )
    return result.scalar_one_or_none()


async def _fuzzy_find_model(db: AsyncSession, name: str) -> Optional[Model]:
    """Fuzzy match a model name against the models table."""
    result = await db.execute(
        select(Model).where(
            (Model.model_id.ilike(f"%{name}%"))
            | (Model.display_name.ilike(f"%{name}%"))
        ).where(Model.is_active == True)
    )
    return result.scalar_one_or_none()


async def _log_modification(
    db: AsyncSession,
    *,
    modification_type: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before_value: Optional[dict],
    after_value: Optional[dict],
    reason: str,
    conversation_id: Optional[str] = None,
) -> None:
    """Log a system modification for audit trail."""
    try:
        conv_uuid = uuid.UUID(conversation_id) if conversation_id else None
        mod = SystemModification(
            id=uuid.uuid4(),
            modification_type=modification_type,
            entity_type=entity_type,
            entity_id=entity_id,
            before_value=before_value,
            after_value=after_value,
            reason=reason,
            conversation_id=conv_uuid,
        )
        db.add(mod)
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to log modification: {e}")
