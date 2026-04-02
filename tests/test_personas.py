"""
test_personas.py - Tests for persona management endpoints.

Covers:
  GET    /v1/personas
  POST   /v1/personas
  GET    /v1/personas/{id}
  PATCH  /v1/personas/{id}
  DELETE /v1/personas/{id}
"""

import uuid
import pytest


class TestListPersonas:
    def test_list_personas_returns_200(self, client):
        """GET /v1/personas should return 200."""
        r = client.get("/v1/personas")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_personas_returns_list_or_dict(self, client):
        """GET /v1/personas should return a JSON list or object."""
        r = client.get("/v1/personas")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_list_personas_no_auth_rejected(self, base_url):
        """GET /v1/personas without auth should return 401/403."""
        import httpx
        with httpx.Client(base_url=base_url, timeout=10.0) as c:
            r = c.get("/v1/personas")
            assert r.status_code in (401, 403), f"Expected auth error, got {r.status_code}"


class TestPersonaCRUD:
    @pytest.fixture(autouse=True)
    def setup_persona(self, client):
        """Create a test persona and clean it up after the test."""
        payload = {
            "name": f"TestPersona-{uuid.uuid4().hex[:8]}",
            "description": "A test persona created by pytest",
            "system_prompt": "You are a helpful test assistant.",
            "avatar": None,
        }
        r = client.post("/v1/personas", json=payload)
        assert r.status_code in (200, 201), f"Setup failed: {r.status_code} {r.text}"
        self.persona = r.json()
        self.persona_id = self.persona.get("id") or self.persona.get("persona", {}).get("id")
        yield
        if self.persona_id:
            client.delete(f"/v1/personas/{self.persona_id}")

    def test_create_persona_has_id(self, client):
        """POST /v1/personas should return the created persona with an id."""
        assert self.persona_id is not None, "Created persona has no id"

    def test_get_persona_by_id(self, client):
        """GET /v1/personas/{id} should return the persona we created."""
        r = client.get(f"/v1/personas/{self.persona_id}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        persona_data = data.get("persona", data)
        assert str(persona_data.get("id")) == str(self.persona_id)

    def test_get_persona_404_for_nonexistent(self, client):
        """GET /v1/personas/{id} with a nonexistent id should return 404."""
        r = client.get("/v1/personas/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_update_persona_description(self, client):
        """PATCH /v1/personas/{id} should update the persona's description."""
        r = client.patch(
            f"/v1/personas/{self.persona_id}",
            json={"description": "Updated by pytest"}
        )
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"

    def test_update_persona_system_prompt(self, client):
        """PATCH /v1/personas/{id} should allow updating system_prompt."""
        r = client.patch(
            f"/v1/personas/{self.persona_id}",
            json={"system_prompt": "You are an updated test assistant."}
        )
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"

    def test_update_nonexistent_persona_returns_404(self, client):
        """PATCH /v1/personas/{id} with bogus id should return 404."""
        r = client.patch("/v1/personas/00000000-0000-0000-0000-000000000000", json={"description": "x"})
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_delete_persona_returns_success(self, client):
        """DELETE /v1/personas/{id} should return 200 or 204."""
        r = client.delete(f"/v1/personas/{self.persona_id}")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"
        self.persona_id = None  # Prevent double-delete in teardown

    def test_delete_nonexistent_persona_returns_404(self, client):
        """DELETE /v1/personas/{id} with bogus id should return 404."""
        r = client.delete("/v1/personas/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


class TestCreatePersonaValidation:
    def test_create_persona_missing_name_returns_422(self, client):
        """POST /v1/personas without a name should return 422."""
        r = client.post("/v1/personas", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
