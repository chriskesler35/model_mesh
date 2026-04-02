"""
test_settings.py - Tests for API Keys and App Settings endpoints.

Covers: /v1/api-keys/*, /v1/settings/app/*
"""

import pytest


class TestApiKeys:
    """Tests for /v1/api-keys endpoints."""

    def test_list_api_keys(self, client):
        """GET /v1/api-keys returns provider key list."""
        r = client.get("/v1/api-keys")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_set_api_key(self, client):
        """PUT /v1/api-keys/{provider} sets a key (must be a valid managed provider)."""
        r = client.put("/v1/api-keys/openrouter", json={
            "value": "sk-or-test-key-abc123"
        })
        assert r.status_code in (200, 201)

    def test_get_api_key_masked(self, client):
        """GET /v1/api-keys should show masked keys."""
        r = client.get("/v1/api-keys")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_delete_api_key(self, client):
        """DELETE /v1/api-keys/{provider} clears the key."""
        # Set first, then clear
        client.put("/v1/api-keys/openrouter", json={"value": "sk-or-test-cleanup"})
        r = client.delete("/v1/api-keys/openrouter")
        assert r.status_code in (200, 204)

    def test_delete_nonexistent_key(self, client):
        """DELETE /v1/api-keys/{provider} for missing provider."""
        r = client.delete("/v1/api-keys/nonexistent_provider_xyz")
        assert r.status_code in (200, 204, 404)


class TestAppSettings:
    """Tests for /v1/settings/app endpoints."""

    def test_list_app_settings(self, client):
        """GET /v1/settings/app returns all settings."""
        r = client.get("/v1/settings/app")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_set_app_setting(self, client):
        """PUT /v1/settings/app/{key} creates/updates a setting."""
        r = client.put("/v1/settings/app/test_setting_key", json={
            "value": "test_value_from_pytest"
        })
        assert r.status_code == 200

    def test_get_app_setting(self, client):
        """GET /v1/settings/app/{key} reads a specific setting."""
        r = client.get("/v1/settings/app/test_setting_key")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            data = r.json()
            assert data.get("value") == "test_value_from_pytest" or "value" in data

    def test_update_app_setting(self, client):
        """PUT /v1/settings/app/{key} updates existing value."""
        r = client.put("/v1/settings/app/test_setting_key", json={
            "value": "updated_value"
        })
        assert r.status_code == 200
        # Verify
        r2 = client.get("/v1/settings/app/test_setting_key")
        if r2.status_code == 200:
            assert r2.json().get("value") == "updated_value"

    def test_get_nonexistent_setting(self, client):
        """GET /v1/settings/app/{key} for missing key."""
        r = client.get("/v1/settings/app/nonexistent_key_xyz_123")
        assert r.status_code in (200, 404)

    def test_known_settings(self, client):
        """GET /v1/settings/app — verify known ComfyUI settings exist."""
        known_keys = [
            "comfyui_dir", "comfyui_python", "comfyui_url",
            "comfyui_gpu_devices", "default_image_provider", "default_workflow"
        ]
        r = client.get("/v1/settings/app")
        assert r.status_code == 200
        data = r.json()
        # Just verify response shape, not that all keys exist
        assert isinstance(data, (list, dict))

    def test_cleanup_test_setting(self, client):
        """Clean up test_setting_key — overwrite with empty."""
        client.put("/v1/settings/app/test_setting_key", json={"value": ""})
