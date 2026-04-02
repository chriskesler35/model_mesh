"""
test_identity.py - Tests for identity, soul, and user endpoints.

Covers:
  GET  /v1/identity/status
  GET  /v1/identity/soul
  PUT  /v1/identity/soul
  GET  /v1/identity/user
  PUT  /v1/identity/user
  GET  /v1/identity/identity-file
  PUT  /v1/identity/identity-file
  POST /v1/identity/setup
"""

import pytest


class TestIdentityStatus:
    def test_identity_status_returns_200(self, client):
        """GET /v1/identity/status should return 200."""
        r = client.get("/v1/identity/status")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_identity_status_returns_dict(self, client):
        """GET /v1/identity/status should return a JSON object."""
        r = client.get("/v1/identity/status")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)


class TestIdentitySoul:
    def test_get_soul_returns_200(self, client):
        """GET /v1/identity/soul should return 200."""
        r = client.get("/v1/identity/soul")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_get_soul_returns_content(self, client):
        """GET /v1/identity/soul should return a JSON object with soul content."""
        r = client.get("/v1/identity/soul")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    @pytest.mark.destructive
    def test_put_soul_updates_content(self, client):
        """PUT /v1/identity/soul should update and return soul content."""
        # First get the current soul content to restore it
        r_get = client.get("/v1/identity/soul")
        original = r_get.json() if r_get.status_code == 200 else {}

        r = client.put(
            "/v1/identity/soul",
            json={"content": "Test soul content from pytest. This is temporary."}
        )
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"

        # Restore original if possible
        if r_get.status_code == 200 and original:
            client.put("/v1/identity/soul", json=original)

    def test_put_soul_missing_content_returns_422(self, client):
        """PUT /v1/identity/soul without content should return 422."""
        r = client.put("/v1/identity/soul", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


class TestIdentityUser:
    def test_get_identity_user_returns_200(self, client):
        """GET /v1/identity/user should return 200."""
        r = client.get("/v1/identity/user")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_get_identity_user_returns_dict(self, client):
        """GET /v1/identity/user should return a JSON object."""
        r = client.get("/v1/identity/user")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    @pytest.mark.destructive
    def test_put_identity_user_updates(self, client):
        """PUT /v1/identity/user should update user identity."""
        r = client.put(
            "/v1/identity/user",
            json={"content": "Test user identity from pytest. Temporary."}
        )
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"


class TestIdentityFile:
    def test_get_identity_file_returns_200(self, client):
        """GET /v1/identity/identity-file should return 200."""
        r = client.get("/v1/identity/identity-file")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_get_identity_file_returns_dict(self, client):
        """GET /v1/identity/identity-file should return a JSON object."""
        r = client.get("/v1/identity/identity-file")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    @pytest.mark.destructive
    def test_put_identity_file_updates(self, client):
        """PUT /v1/identity/identity-file should update the identity file."""
        # Get current first to avoid data loss
        r_get = client.get("/v1/identity/identity-file")
        original = r_get.json() if r_get.status_code == 200 else {}

        r = client.put(
            "/v1/identity/identity-file",
            json={"content": "Test identity file from pytest. Temporary."}
        )
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"

        # Restore
        if r_get.status_code == 200 and original:
            client.put("/v1/identity/identity-file", json=original)


class TestIdentitySetup:
    def test_setup_endpoint_returns_success_or_already_setup(self, client):
        """POST /v1/identity/setup should return 200 or indicate already configured."""
        r = client.post("/v1/identity/setup", json={
            "soul": "Test AI identity from pytest",
            "user": "Test user from pytest",
            "identity": "Test identity from pytest"
        })
        assert r.status_code in (200, 201, 400, 409, 422), (
            f"Unexpected: {r.status_code}: {r.text}"
        )
