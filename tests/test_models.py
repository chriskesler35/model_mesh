"""
test_models.py - Tests for model management endpoints.

Covers:
  GET    /v1/models
  POST   /v1/models
  GET    /v1/models/{id}
  PATCH  /v1/models/{id}
  DELETE /v1/models/{id}
  GET    /v1/models/provider/{provider_name}
"""

import uuid
import pytest


TEST_MODEL_NAME = f"test-model-{uuid.uuid4().hex[:8]}"


class TestListModels:
    def test_list_models_returns_200(self, client):
        """GET /v1/models should return 200."""
        r = client.get("/v1/models")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_models_returns_list_or_dict(self, client):
        """GET /v1/models should return a JSON array or object containing models."""
        r = client.get("/v1/models")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_list_models_no_auth_rejected(self, base_url):
        """GET /v1/models without auth should be rejected (401/403)."""
        import httpx
        with httpx.Client(base_url=base_url, timeout=10.0) as c:
            r = c.get("/v1/models")
            assert r.status_code in (401, 403), f"Expected auth error, got {r.status_code}"


class TestModelCRUD:
    @pytest.fixture(autouse=True)
    def created_model(self, client):
        """Create a test model before each test and delete it after."""
        # Look up the Ollama provider UUID
        providers_res = client.get("/v1/providers")
        providers = providers_res.json()
        provider_list = providers if isinstance(providers, list) else providers.get("data", [])
        ollama_provider = next((p for p in provider_list if "ollama" in p.get("name", "").lower()), None)
        if not ollama_provider:
            pytest.skip("No Ollama provider available")
        payload = {
            "name": f"test-model-{uuid.uuid4().hex[:8]}",
            "provider_id": ollama_provider["id"],
            "model_id": "llama3.2:1b",
            "display_name": "Test Model",
            "description": "Test model created by pytest",
            "context_window": 4096,
        }
        r = client.post("/v1/models", json=payload)
        assert r.status_code in (200, 201), f"Setup failed: {r.status_code} {r.text}"
        self.model = r.json()
        self.model_id = self.model.get("id") or self.model.get("model", {}).get("id")
        yield
        if self.model_id:
            client.delete(f"/v1/models/{self.model_id}")

    def test_create_model_returns_id(self, client):
        """POST /v1/models should return the created model with an id."""
        assert self.model_id is not None, "Created model has no id"

    def test_get_model_by_id(self, client):
        """GET /v1/models/{id} should return the model we created."""
        r = client.get(f"/v1/models/{self.model_id}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        # The returned object should reference our model
        model_data = data.get("model", data)
        assert model_data.get("id") == self.model_id or str(model_data.get("id")) == str(self.model_id)

    def test_get_model_404_for_nonexistent(self, client):
        """GET /v1/models/{id} with a bogus id should return 404."""
        r = client.get("/v1/models/nonexistent-fake-id-99999")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_update_model_description(self, client):
        """PATCH /v1/models/{id} should update the model's description."""
        new_desc = "Updated description from pytest"
        r = client.patch(f"/v1/models/{self.model_id}", json={"description": new_desc})
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"

    def test_update_model_404_for_nonexistent(self, client):
        """PATCH /v1/models/{id} with a bogus id should return 404."""
        r = client.patch("/v1/models/nonexistent-fake-id-99999", json={"description": "x"})
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_delete_model_returns_success(self, client):
        """DELETE /v1/models/{id} should return 200 or 204."""
        r = client.delete(f"/v1/models/{self.model_id}")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"
        self.model_id = None  # Prevent double-delete in teardown

    def test_delete_model_404_for_nonexistent(self, client):
        """DELETE /v1/models/{id} with a bogus id should return 404."""
        r = client.delete("/v1/models/nonexistent-fake-id-99999")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


class TestCreateModelValidation:
    def test_create_model_missing_required_fields_returns_422(self, client):
        """POST /v1/models with empty payload should return 422 Unprocessable Entity."""
        r = client.post("/v1/models", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


class TestModelsByProvider:
    def test_get_models_by_provider_returns_200_or_404(self, client):
        """GET /v1/models/provider/{provider_name} should return 200 or 404."""
        r = client.get("/v1/models/provider/ollama")
        assert r.status_code in (200, 404), f"Expected 200/404, got {r.status_code}: {r.text}"

    def test_get_models_by_unknown_provider(self, client):
        """GET /v1/models/provider/{provider_name} for unknown provider returns 200 (empty) or 404."""
        r = client.get("/v1/models/provider/totally_fake_provider_xyz")
        assert r.status_code in (200, 404), f"Unexpected status {r.status_code}: {r.text}"
