"""Execute model management commands from chat.

Handles parsed commands with entity_type="model" and routes to the
appropriate CRUD operation. All modifications are logged to the
system_modifications table for auditability.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model import Model
from app.models.provider import Provider
from app.models.user_profile import SystemModification

logger = logging.getLogger(__name__)


async def execute_model_command(
    command: dict,
    db: AsyncSession,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Execute a model-related chat command and return a response string.

    Args:
        command: Parsed command dict with action, entity_type, params.
        db: Async database session.
        conversation_id: Optional conversation ID for audit logging.

    Returns:
        Formatted response string to display in chat.
    """
    action = command["action"]
    params = command.get("params", {})

    handlers = {
        "list": _list_models,
        "create": _add_model,
        "delete": _delete_model,
        "switch": _switch_model,
    }

    handler = handlers.get(action)
    if not handler:
        return f"Unknown model action: {action}"

    return await handler(db, params, conversation_id=conversation_id)


# ── List models ───────────────────────────────────────────────────────────────

async def _list_models(
    db: AsyncSession,
    params: dict,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """List all active models as a formatted markdown table."""
    result = await db.execute(
        select(Model, Provider)
        .outerjoin(Provider, Model.provider_id == Provider.id)
        .where(Model.is_active == True)
        .order_by(Model.display_name)
    )
    rows = result.all()

    if not rows:
        return "No models configured. Use 'add model <name> from <provider>' to add one."

    lines = ["**Your Models:**\n"]
    lines.append("| Model | Provider | Context | Cost (in/out per 1M) |")
    lines.append("|-------|----------|---------|---------------------|")

    for model, provider in rows:
        prov_name = provider.display_name if provider else "Unknown"
        ctx = f"{model.context_window:,}" if model.context_window else "\u2014"
        cost_in = f"${float(model.cost_per_1m_input):.2f}" if model.cost_per_1m_input else "Free"
        cost_out = f"${float(model.cost_per_1m_output):.2f}" if model.cost_per_1m_output else "Free"
        name = model.display_name or model.model_id
        lines.append(f"| {name} | {prov_name} | {ctx} | {cost_in} / {cost_out} |")

    lines.append(f"\n*{len(rows)} model(s) active*")
    return "\n".join(lines)


# ── Add model ─────────────────────────────────────────────────────────────────

async def _add_model(
    db: AsyncSession,
    params: dict,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Add a new model to the system."""
    name = params.get("name", "").strip()
    provider_name = params.get("provider", "").strip()

    if not name:
        return "Please specify a model name. Example: 'add model gpt-4 from openai'"

    # Check if model already exists (active or inactive)
    existing_result = await db.execute(
        select(Model).where(Model.model_id == name)
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        if existing.is_active:
            return f"Model '{name}' already exists and is active."
        # Reactivate a previously deactivated model
        existing.is_active = True
        await db.commit()
        await _log_modification(
            db,
            modification_type="reactivate_model",
            entity_type="model",
            entity_id=existing.id,
            before_value={"is_active": False},
            after_value={"is_active": True},
            reason=f"Reactivated via chat command",
            conversation_id=conversation_id,
        )
        return f"Model **{name}** was previously deactivated and has been reactivated."

    # Find provider if specified
    provider = None
    if provider_name:
        prov_result = await db.execute(
            select(Provider).where(
                Provider.name.ilike(f"%{provider_name}%")
                | Provider.display_name.ilike(f"%{provider_name}%")
            )
        )
        provider = prov_result.scalar_one_or_none()
        if not provider:
            # List available providers so the user can pick
            all_provs_result = await db.execute(
                select(Provider.name, Provider.display_name).where(Provider.is_active == True)
            )
            prov_rows = all_provs_result.all()
            if prov_rows:
                prov_list = ", ".join(f"{r.display_name or r.name}" for r in prov_rows)
                return f"Provider '{provider_name}' not found. Available providers: {prov_list}"
            return f"Provider '{provider_name}' not found and no providers are configured."
    else:
        # No provider specified -- try to find one from the model name or use first active
        first_prov_result = await db.execute(
            select(Provider).where(Provider.is_active == True).limit(1)
        )
        provider = first_prov_result.scalar_one_or_none()
        if not provider:
            return "No providers configured. Please add a provider first in Settings."

    # Create the model
    new_model = Model(
        id=uuid.uuid4(),
        model_id=name,
        display_name=name,
        provider_id=provider.id,
        is_active=True,
    )
    db.add(new_model)
    await db.commit()
    await db.refresh(new_model)

    # Log to system_modifications
    await _log_modification(
        db,
        modification_type="add_model",
        entity_type="model",
        entity_id=new_model.id,
        before_value=None,
        after_value={
            "model_id": name,
            "provider": provider.display_name or provider.name,
            "provider_id": str(provider.id),
        },
        reason=f"Added via chat command",
        conversation_id=conversation_id,
    )

    prov_display = provider.display_name or provider.name
    return f"Model **{name}** added (provider: {prov_display}). It's now available for use."


# ── Delete (soft) model ───────────────────────────────────────────────────────

async def _delete_model(
    db: AsyncSession,
    params: dict,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Soft-delete a model by setting is_active=False."""
    name = params.get("name", "").strip()
    if not name:
        return "Please specify which model to remove. Example: 'delete model gpt-4'"

    result = await db.execute(
        select(Model).where(
            (Model.model_id.ilike(f"%{name}%"))
            | (Model.display_name.ilike(f"%{name}%"))
        ).where(Model.is_active == True)
    )
    model = result.scalar_one_or_none()

    if not model:
        return f"Model '{name}' not found or already deactivated. Use 'list models' to see active models."

    before = {
        "model_id": model.model_id,
        "display_name": model.display_name,
        "is_active": True,
    }

    model.is_active = False
    await db.commit()

    # Log to system_modifications
    await _log_modification(
        db,
        modification_type="delete_model",
        entity_type="model",
        entity_id=model.id,
        before_value=before,
        after_value={"is_active": False},
        reason=f"Deactivated via chat command",
        conversation_id=conversation_id,
    )

    display = model.display_name or model.model_id
    return f"Model **{display}** has been deactivated. It can be reactivated with 'add model {model.model_id}'."


# ── Switch/info about a model ────────────────────────────────────────────────

async def _switch_model(
    db: AsyncSession,
    params: dict,
    *,
    conversation_id: Optional[str] = None,
) -> str:
    """Provide info on how to use a specific model."""
    name = params.get("name", "").strip()
    if not name:
        return "Please specify which model to switch to. Example: 'switch to model claude-sonnet'"

    result = await db.execute(
        select(Model, Provider)
        .outerjoin(Provider, Model.provider_id == Provider.id)
        .where(
            (Model.model_id.ilike(f"%{name}%"))
            | (Model.display_name.ilike(f"%{name}%"))
        )
        .where(Model.is_active == True)
    )
    row = result.first()

    if not row:
        return f"Model '{name}' not found. Use 'list models' to see available models."

    model, provider = row
    display = model.display_name or model.model_id
    prov = provider.display_name if provider else "Unknown"
    ctx = f"{model.context_window:,}" if model.context_window else "not specified"

    return (
        f"**{display}** ({prov})\n"
        f"- Context window: {ctx}\n"
        f"- Active: Yes\n\n"
        f"To use this model, set it as the primary model on a persona in "
        f"**Settings > Personas**, or specify it when creating a pipeline."
    )


# ── Audit logging ─────────────────────────────────────────────────────────────

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
        logger.warning(f"Failed to log system modification: {e}")
        # Don't fail the command if logging fails
