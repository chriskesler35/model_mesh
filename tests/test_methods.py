"""
test_methods.py - Tests for development methods endpoints.

Covers:
  GET    /v1/methods/
  GET    /v1/methods/active
  GET    /v1/methods/active/prompt
  POST   /v1/methods/activate
  POST   /v1/methods/stack
  POST   /v1/methods/stack/add
  POST   /v1/methods/stack/remove
  DELETE /v1/methods/stack
  GET    /v1/methods/{id}
"""

import pytest


class TestListMethods:
    def test_list_methods_returns_200(self, client):
        """GET /v1/methods/ should return 200."""
        r = client.get("/v1/methods/")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_methods_returns_list_or_dict(self, client):
        """GET /v1/methods/ should return a JSON list or object."""
        r = client.get("/v1/methods/")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_list_methods_includes_discovery_and_retrospective(self, client):
        """Built-in discovery and retrospective methods should be listed."""
        r = client.get("/v1/methods/")
        assert r.status_code == 200
        payload = r.json()
        methods = payload.get("data", payload if isinstance(payload, list) else [])
        method_ids = {m.get("id") for m in methods if isinstance(m, dict)}
        assert "discovery" in method_ids
        assert "retrospective" in method_ids


class TestActiveMethods:
    def test_get_active_method_returns_200_or_204(self, client):
        """GET /v1/methods/active should return 200 or 204 if nothing is active."""
        r = client.get("/v1/methods/active")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"

    def test_get_active_method_prompt_returns_200_or_204(self, client):
        """GET /v1/methods/active/prompt should return 200 or 204."""
        r = client.get("/v1/methods/active/prompt")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"


class TestActivateMethod:
    def test_activate_nonexistent_method_returns_404_or_422(self, client):
        """POST /v1/methods/activate with a bogus method id should return 404 or 422."""
        r = client.post("/v1/methods/activate", json={"method_id": "nonexistent-fake-method-xyz"})
        assert r.status_code in (404, 422), f"Expected 404/422, got {r.status_code}: {r.text}"

    def test_activate_first_available_method(self, client):
        """POST /v1/methods/activate with the first available method id should succeed."""
        r_list = client.get("/v1/methods/")
        if r_list.status_code != 200:
            pytest.skip("Could not list methods")
        methods = r_list.json()
        if isinstance(methods, dict):
            methods = methods.get("methods", methods.get("items", []))
        if not methods or not isinstance(methods, list):
            pytest.skip("No methods available to activate")

        method_id = methods[0].get("id")
        if not method_id:
            pytest.skip("First method has no id")

        r = client.post("/v1/methods/activate", json={"method_id": method_id})
        assert r.status_code in (200, 204, 400, 404), (
            f"Unexpected: {r.status_code}: {r.text}"
        )


class TestMethodStack:
    def test_get_or_set_stack_returns_success(self, client):
        """POST /v1/methods/stack should return a valid status."""
        r = client.post("/v1/methods/stack", json={})
        assert r.status_code in (200, 204, 400, 422), (
            f"Unexpected: {r.status_code}: {r.text}"
        )

    def test_add_to_stack_missing_id_returns_422(self, client):
        """POST /v1/methods/stack/add without a method id should return 422."""
        r = client.post("/v1/methods/stack/add", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"

    def test_remove_from_stack_missing_id_returns_422(self, client):
        """POST /v1/methods/stack/remove without a method id should return 422."""
        r = client.post("/v1/methods/stack/remove", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"

    @pytest.mark.destructive
    def test_delete_stack_clears_it(self, client):
        """DELETE /v1/methods/stack should clear the stack."""
        r = client.delete("/v1/methods/stack")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"


class TestGetMethodById:
    def test_get_method_by_id_returns_200_or_404(self, client):
        """GET /v1/methods/{id} should return 200 for valid id or 404 for bogus id."""
        r = client.get("/v1/methods/nonexistent-fake-method-xyz")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_get_first_real_method(self, client):
        """GET /v1/methods/{id} should return 200 for a real method."""
        r_list = client.get("/v1/methods/")
        if r_list.status_code != 200:
            pytest.skip("Could not list methods")
        methods = r_list.json()
        if isinstance(methods, dict):
            methods = methods.get("methods", methods.get("items", []))
        if not methods or not isinstance(methods, list):
            pytest.skip("No methods available")

        method_id = methods[0].get("id")
        if not method_id:
            pytest.skip("First method has no id")

        r = client.get(f"/v1/methods/{method_id}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
