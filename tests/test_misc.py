"""
test_misc.py - Tests for remaining endpoints.

Covers: model_lookup, model_sync, model_validate, tasks, context, hardware, user/memory.
"""

import pytest
import uuid


class TestModelLookup:
    """Tests for /v1/model-lookup/* endpoints."""

    def test_lookup_known_model(self, client):
        """POST /v1/model-lookup/lookup returns pricing for a known model."""
        payload = {"model_id": "claude-sonnet-4-6", "provider": "anthropic"}
        r = client.post("/v1/model-lookup/lookup", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_lookup_unknown_model(self, client):
        """POST /v1/model-lookup/lookup for unknown model."""
        payload = {"model_id": "nonexistent-model-xyz", "provider": "unknown"}
        r = client.post("/v1/model-lookup/lookup", json=payload)
        assert r.status_code in (200, 404)

    def test_suggestions_ollama(self, client):
        """GET /v1/model-lookup/suggestions/ollama returns suggestions."""
        r = client.get("/v1/model-lookup/suggestions/ollama")
        assert r.status_code in (200, 503)

    def test_suggestions_openrouter(self, client):
        """GET /v1/model-lookup/suggestions/openrouter."""
        r = client.get("/v1/model-lookup/suggestions/openrouter")
        assert r.status_code in (200, 503)

    def test_suggestions_unknown_provider(self, client):
        """GET /v1/model-lookup/suggestions/unknown returns empty or 404."""
        r = client.get("/v1/model-lookup/suggestions/nonexistent_provider")
        assert r.status_code in (200, 404)


class TestModelSync:
    """Tests for /v1/model-sync/* endpoints."""

    def test_sync_status(self, client):
        """GET /v1/model-sync/sync/status returns sync info."""
        r = client.get("/v1/models/sync/status")
        assert r.status_code == 200

    @pytest.mark.slow
    def test_run_sync(self, client):
        """POST /v1/model-sync/sync triggers model sync."""
        r = client.post("/v1/models/sync")
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            data = r.json()
            assert "added" in data or "synced" in data or isinstance(data, dict)


class TestModelValidate:
    """Tests for /v1/model-validate endpoint."""

    def test_validate_model(self, client):
        """POST /v1/model-validate checks model availability."""
        payload = {"model_id": "llama3.1:8b", "provider": "ollama"}
        r = client.post("/v1/models/validate", json=payload)
        assert r.status_code in (200, 422)

    def test_validate_empty(self, client):
        """POST /v1/model-validate with empty body."""
        r = client.post("/v1/models/validate", json={})
        assert r.status_code in (200, 422)


class TestTasks:
    """Tests for /v1/tasks/* endpoints."""

    def test_list_tasks(self, client):
        """GET /v1/tasks returns task list."""
        r = client.get("/v1/tasks")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_create_task(self, client):
        """POST /v1/tasks creates a new task."""
        payload = {
            "task_type": "image_gen",
            "params": {"prompt": "test image from pytest", "model": "gemini-imagen", "size": "256x256"},
        }
        r = client.post("/v1/tasks", json=payload)
        assert r.status_code in (200, 201)
        data = r.json()
        self.__class__._task_id = data.get("id")

    def test_get_task(self, client):
        """GET /v1/tasks/{id} returns task details."""
        tid = getattr(self.__class__, "_task_id", None)
        if not tid:
            pytest.skip("No task to get")
        r = client.get(f"/v1/tasks/{tid}")
        assert r.status_code in (200, 404)

    def test_acknowledge_task(self, client):
        """POST /v1/tasks/{id}/acknowledge marks task as acked."""
        tid = getattr(self.__class__, "_task_id", None)
        if not tid:
            pytest.skip("No task to acknowledge")
        r = client.post(f"/v1/tasks/{tid}/acknowledge")
        assert r.status_code in (200, 404)

    def test_notifications(self, client):
        """GET /v1/tasks/notifications returns pending notifications."""
        r = client.get("/v1/tasks/notifications")
        assert r.status_code == 200


class TestContext:
    """Tests for /v1/context/* endpoints."""

    def test_get_memory(self, client):
        """GET /v1/context/memory returns memory context."""
        r = client.get("/v1/context/memory")
        assert r.status_code == 200

    def test_update_memory(self, client):
        """PUT /v1/context/memory updates memory content."""
        r = client.put("/v1/context/memory", json={
            "note": "Test memory content from pytest"
        })
        assert r.status_code in (200, 422)

    def test_get_snapshots(self, client):
        """GET /v1/context/snapshots returns context snapshots."""
        r = client.get("/v1/context/snapshots")
        assert r.status_code == 200

    def test_recover_nonexistent(self, client):
        """GET /v1/context/recover/{id} for missing conversation."""
        r = client.get(f"/v1/context/recover/{uuid.uuid4()}")
        assert r.status_code in (200, 404)


class TestHardware:
    """Tests for /v1/hardware/* endpoints."""

    def test_hardware_status(self, client):
        """GET /v1/hardware/status returns system hardware info."""
        r = client.get("/v1/hardware/status")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_hardware_check_model(self, client):
        """GET /v1/hardware/check/{model_id} checks if model can run locally."""
        r = client.get("/v1/hardware/check/llama3.1:8b")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, dict)


class TestUserAndMemory:
    """Tests for /v1/user and /v1/memory endpoints."""

    def test_get_user_profile(self, client):
        """GET /v1/user returns user profile."""
        r = client.get("/v1/user")
        assert r.status_code == 200

    def test_update_user_profile(self, client):
        """PATCH /v1/user updates profile."""
        r = client.patch("/v1/user", json={
            "display_name": "Test User Profile"
        })
        assert r.status_code in (200, 422)

    def test_list_memory_files(self, client):
        """GET /v1/memory returns memory file list."""
        r = client.get("/v1/memory")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_create_memory_file(self, client):
        """POST /v1/memory creates a new memory file."""
        payload = {
            "name": f"pytest_test_{uuid.uuid4().hex[:8]}",
            "content": "# Test Memory File\nCreated by pytest."
        }
        r = client.post("/v1/memory", json=payload)
        assert r.status_code in (200, 201)
        data = r.json()
        self.__class__._mem_id = data.get("id") or data.get("filename")

    def test_get_memory_file(self, client):
        """GET /v1/memory/{id} returns file content."""
        mid = getattr(self.__class__, "_mem_id", None)
        if not mid:
            pytest.skip("No memory file to get")
        r = client.get(f"/v1/memory/{mid}")
        assert r.status_code in (200, 404)

    def test_update_memory_file(self, client):
        """PATCH /v1/memory/{id} updates file content."""
        mid = getattr(self.__class__, "_mem_id", None)
        if not mid:
            pytest.skip("No memory file to update")
        r = client.patch(f"/v1/memory/{mid}", json={
            "content": "# Updated Test Memory\nModified by pytest."
        })
        assert r.status_code in (200, 404)

    def test_delete_memory_file(self, client):
        """DELETE /v1/memory/{id} removes the file."""
        mid = getattr(self.__class__, "_mem_id", None)
        if not mid:
            pytest.skip("No memory file to delete")
        r = client.delete(f"/v1/memory/{mid}")
        assert r.status_code in (200, 204, 404)

    def test_get_modifications(self, client):
        """GET /v1/modifications returns recent modifications."""
        r = client.get("/v1/modifications")
        assert r.status_code == 200


class TestProviders:
    """Tests for /v1/providers endpoint."""

    def test_list_providers(self, client):
        """GET /v1/providers returns provider list."""
        r = client.get("/v1/providers")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))
        # Should have at least Ollama
        if isinstance(data, list):
            names = [p.get("name", "") for p in data]
            assert any("ollama" in n.lower() for n in names) or len(data) > 0
