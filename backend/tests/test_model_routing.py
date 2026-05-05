"""Tests for model routing policy and preview helpers."""

import pytest

from app.models.model import Model
from app.models.provider import Provider
from app.services.model_routing import (
    DEFAULT_ROUTING_POLICY,
    get_routing_policy,
    preview_route,
    set_routing_policy,
)


@pytest.mark.asyncio
async def test_get_routing_policy_defaults(db_session):
    policy = await get_routing_policy(db_session)
    assert isinstance(policy, dict)
    assert policy.get("version") == DEFAULT_ROUTING_POLICY["version"]
    assert "defaults" in policy


@pytest.mark.asyncio
async def test_set_routing_policy_roundtrip(db_session):
    new_policy = {
        "version": 2,
        "defaults": {"budget_mode": "cost_saver"},
        "task_profiles": {"chat": {"preferred_capabilities": ["chat"]}},
        "provider_preferences": {"cost_saver": ["openrouter", "openai"]},
    }

    await set_routing_policy(db_session, new_policy)
    loaded = await get_routing_policy(db_session)

    assert loaded.get("version") == 2
    assert loaded.get("defaults", {}).get("budget_mode") == "cost_saver"


@pytest.mark.asyncio
async def test_preview_route_prefers_lower_cost_for_cost_saver(db_session):
    provider = Provider(name="openrouter", display_name="OpenRouter", is_active=True)
    db_session.add(provider)
    await db_session.flush()

    cheap = Model(
        provider_id=provider.id,
        model_id="cheap-model",
        display_name="Cheap Model",
        cost_per_1m_input=0.1,
        cost_per_1m_output=0.2,
        context_window=128000,
        capabilities={"chat": True, "streaming": True},
        is_active=True,
        validation_status="validated",
    )
    expensive = Model(
        provider_id=provider.id,
        model_id="expensive-model",
        display_name="Expensive Model",
        cost_per_1m_input=10.0,
        cost_per_1m_output=20.0,
        context_window=128000,
        capabilities={"chat": True, "streaming": True},
        is_active=True,
        validation_status="validated",
    )
    db_session.add_all([cheap, expensive])
    await db_session.commit()

    result = await preview_route(
        db_session,
        task_type="chat",
        prompt_preview="Summarize this request.",
        budget_mode="cost_saver",
        risk_level="normal",
    )

    assert result.get("selected") is not None
    assert result["selected"]["model_id"] == "cheap-model"
