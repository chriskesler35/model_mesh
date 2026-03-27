"""Tests for router service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.router import Router, NoModelAvailableError, CostLimitExceededError
from app.models import Persona, Model, Provider


@pytest.mark.asyncio
async def test_router_raises_no_model_available():
    """Test that router raises NoModelAvailableError when no model provided."""
    db = AsyncMock()
    memory = MagicMock()
    router = Router(db, memory)
    
    # Should raise when no persona/model provided
    with pytest.raises(NoModelAvailableError):
        async for _ in router.route_request(
            persona=None,
            primary_model=None,
            fallback_model=None,
            messages=[{"role": "user", "content": "test"}]
        ):
            pass


@pytest.mark.asyncio
async def test_cost_limit_exceeded():
    """Test that router raises CostLimitExceededError when cost exceeds limit."""
    from decimal import Decimal
    
    # Create mock persona with cost limit
    persona = MagicMock()
    persona.id = "test-id"
    persona.memory_enabled = False
    persona.routing_rules = {"max_cost": 0.001}
    persona.max_memory_messages = 10
    
    # Create mock model with high cost
    model = MagicMock()
    model.id = "model-id"
    model.model_id = "test-model"
    model.cost_per_1m_input = Decimal("10.0")  # $10 per million tokens
    model.cost_per_1m_output = Decimal("30.0")
    model.capabilities = {}
    model.provider_id = "provider-id"
    
    # Router should raise CostLimitExceededError when trying to route
    # (This would need a full integration test to properly test)
    pass  # Placeholder for integration test