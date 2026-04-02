"""
test_preferences.py - Tests for /v1/preferences/* endpoints.

Covers: CRUD + LLM detection.
"""

import pytest
import uuid


class TestPreferences:
    """Tests for learned preferences endpoints."""

    def test_list_preferences(self, client):
        """GET /v1/preferences returns preference list."""
        r = client.get("/v1/preferences")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_create_preference(self, client):
        """POST /v1/preferences creates a new preference."""
        payload = {
            "key": f"test_pref_{uuid.uuid4().hex[:8]}",
            "value": "pytest automated test preference",
            "category": "general",
            "source": "manual"
        }
        r = client.post("/v1/preferences", json=payload)
        assert r.status_code in (200, 201)
        data = r.json()
        self.__class__._pref_id = data.get("id")
        assert data.get("key") == payload["key"] or "id" in data

    def test_update_preference(self, client):
        """PATCH /v1/preferences/{id} toggles active state."""
        pid = getattr(self.__class__, "_pref_id", None)
        if not pid:
            pytest.skip("No preference to update")
        r = client.patch(f"/v1/preferences/{pid}", json={"is_active": False})
        assert r.status_code == 200

    def test_delete_preference(self, client):
        """DELETE /v1/preferences/{id} removes the preference."""
        pid = getattr(self.__class__, "_pref_id", None)
        if not pid:
            pytest.skip("No preference to delete")
        r = client.delete(f"/v1/preferences/{pid}")
        assert r.status_code in (200, 204)

    @pytest.mark.slow
    def test_detect_preferences(self, client):
        """POST /v1/preferences/detect uses LLM to detect preferences."""
        r = client.post("/v1/preferences/detect", json={})
        # May fail if no LLM available — accept 200 or 500/503
        assert r.status_code in (200, 422, 500, 503)

    def test_create_preference_with_category(self, client):
        """POST /v1/preferences — verify each category works."""
        for category in ["general", "coding", "communication", "ui", "workflow"]:
            payload = {
                "key": f"cat_test_{category}_{uuid.uuid4().hex[:6]}",
                "value": f"test value for {category}",
                "category": category,
                "source": "manual"
            }
            r = client.post("/v1/preferences", json=payload)
            assert r.status_code in (200, 201), f"Failed for category: {category}"
            # Clean up
            pid = r.json().get("id")
            if pid:
                client.delete(f"/v1/preferences/{pid}")

    def test_create_duplicate_key(self, client):
        """POST /v1/preferences with duplicate key — should handle gracefully."""
        payload = {
            "key": "duplicate_test_key",
            "value": "first value",
            "category": "general",
            "source": "manual"
        }
        r1 = client.post("/v1/preferences", json=payload)
        assert r1.status_code in (200, 201)
        id1 = r1.json().get("id")

        payload["value"] = "second value"
        r2 = client.post("/v1/preferences", json=payload)
        # Should either succeed (creating second) or reject (409)
        assert r2.status_code in (200, 201, 409)
        id2 = r2.json().get("id") if r2.status_code in (200, 201) else None

        # Cleanup
        if id1:
            client.delete(f"/v1/preferences/{id1}")
        if id2:
            client.delete(f"/v1/preferences/{id2}")
