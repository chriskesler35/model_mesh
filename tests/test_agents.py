"""
test_agents.py - Tests for agent management endpoints.

Covers:
  GET    /v1/agents
  POST   /v1/agents
  GET    /v1/agents/defaults
  GET    /v1/agents/{id}
  PATCH  /v1/agents/{id}
  DELETE /v1/agents/{id}
"""

import uuid
import pytest


class TestListAgents:
    def test_list_agents_returns_200(self, client):
        """GET /v1/agents should return 200."""
        r = client.get("/v1/agents")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_agents_returns_list_or_dict(self, client):
        """GET /v1/agents should return a JSON array or object."""
        r = client.get("/v1/agents")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_list_agents_no_auth_rejected(self, base_url):
        """GET /v1/agents without auth should return 401/403."""
        import httpx
        with httpx.Client(base_url=base_url, timeout=10.0) as c:
            r = c.get("/v1/agents")
            assert r.status_code in (401, 403), f"Expected auth error, got {r.status_code}"


class TestAgentDefaults:
    def test_agent_defaults_returns_200(self, client):
        """GET /v1/agents/defaults should return 200."""
        r = client.get("/v1/agents/defaults")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_agent_defaults_returns_dict(self, client):
        """GET /v1/agents/defaults should return a JSON object with default settings."""
        r = client.get("/v1/agents/defaults")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (dict, list))


class TestAgentCRUD:
    @pytest.fixture(autouse=True)
    def setup_agent(self, client):
        """Create a test agent and clean it up after each test."""
        payload = {
            "name": f"TestAgent-{uuid.uuid4().hex[:8]}",
            "agent_type": "coder",
            "description": "A test agent created by pytest",
            "system_prompt": "You are a test agent. Respond concisely.",
        }
        r = client.post("/v1/agents", json=payload)
        assert r.status_code in (200, 201), f"Setup failed: {r.status_code} {r.text}"
        self.agent = r.json()
        self.agent_id = self.agent.get("id") or self.agent.get("agent", {}).get("id")
        yield
        if self.agent_id:
            client.delete(f"/v1/agents/{self.agent_id}")

    def test_create_agent_has_id(self, client):
        """POST /v1/agents should return the created agent with an id."""
        assert self.agent_id is not None, "Created agent has no id"

    def test_get_agent_by_id(self, client):
        """GET /v1/agents/{id} should return the agent we created."""
        r = client.get(f"/v1/agents/{self.agent_id}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        agent_data = data.get("agent", data)
        assert str(agent_data.get("id")) == str(self.agent_id)

    def test_get_agent_404_for_nonexistent(self, client):
        """GET /v1/agents/{id} with bogus id should return 404."""
        r = client.get("/v1/agents/nonexistent-fake-id-99999")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_update_agent_description(self, client):
        """PATCH /v1/agents/{id} should update the agent's description."""
        r = client.patch(
            f"/v1/agents/{self.agent_id}",
            json={"description": "Updated description from pytest"}
        )
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"

    def test_update_nonexistent_agent_returns_404(self, client):
        """PATCH /v1/agents/{id} with bogus id should return 404."""
        r = client.patch("/v1/agents/nonexistent-fake-id-99999", json={"description": "x"})
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_delete_agent_returns_success(self, client):
        """DELETE /v1/agents/{id} should return 200 or 204."""
        r = client.delete(f"/v1/agents/{self.agent_id}")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"
        self.agent_id = None

    def test_delete_nonexistent_agent_returns_404(self, client):
        """DELETE /v1/agents/{id} with bogus id should return 404."""
        r = client.delete("/v1/agents/nonexistent-fake-id-99999")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


class TestCreateAgentValidation:
    def test_create_agent_missing_required_fields_returns_422(self, client):
        """POST /v1/agents with empty payload should return 422."""
        r = client.post("/v1/agents", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
