"""Tests for personas endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_personas_empty(client: AsyncClient):
    """Test listing personas when none exist."""
    response = await client.get("/v1/personas")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["data"]) == 0


@pytest.mark.asyncio
async def test_create_persona(client: AsyncClient):
    """Test creating a persona."""
    response = await client.post(
        "/v1/personas",
        json={
            "name": "test-persona",
            "description": "Test persona",
            "system_prompt": "You are a helpful assistant.",
            "memory_enabled": True,
            "max_memory_messages": 5
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test-persona"
    assert data["memory_enabled"] is True


@pytest.mark.asyncio
async def test_get_persona_by_name(client: AsyncClient):
    """Test getting a persona by name."""
    # Create persona first
    await client.post(
        "/v1/personas",
        json={
            "name": "named-persona",
            "description": "Named persona"
        }
    )
    
    # Get by name
    response = await client.get("/v1/personas/named-persona")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "named-persona"


@pytest.mark.asyncio
async def test_update_persona(client: AsyncClient):
    """Test updating a persona."""
    import uuid
    
    # Create persona
    create_response = await client.post(
        "/v1/personas",
        json={
            "name": "update-test",
            "description": "Original description"
        }
    )
    persona_id = create_response.json()["id"]
    
    # Update
    response = await client.patch(
        f"/v1/personas/{persona_id}",
        json={"description": "Updated description"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_delete_persona(client: AsyncClient):
    """Test deleting a persona."""
    import uuid
    
    # Create persona
    create_response = await client.post(
        "/v1/personas",
        json={"name": "delete-test"}
    )
    persona_id = create_response.json()["id"]
    
    # Delete
    response = await client.delete(f"/v1/personas/{persona_id}")
    assert response.status_code == 200
    
    # Verify deleted
    get_response = await client.get(f"/v1/personas/{persona_id}")
    assert get_response.status_code == 404