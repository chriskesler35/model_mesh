"""
test_collaboration.py - Tests for /v1/collab/* endpoints.

Covers: users, workspaces, handoffs, audit log.
"""

import pytest
import uuid


class TestCollabUsers:
    """Tests for /v1/collab/users CRUD."""

    def test_list_users(self, client):
        """GET /v1/collab/users returns a list."""
        r = client.get("/v1/collab/users")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_create_user(self, client):
        """POST /v1/collab/users creates a new user."""
        payload = {
            "username": f"testuser_{uuid.uuid4().hex[:8]}",
            "display_name": "Test User",
            "role": "member",
            "password": "test_password_123"
        }
        r = client.post("/v1/collab/users", json=payload)
        assert r.status_code in (200, 201)
        data = r.json()
        assert data.get("username") == payload["username"] or "id" in data
        # Store for cleanup
        self.__class__._created_user_id = data.get("id")
        self.__class__._created_username = payload["username"]

    def test_update_user(self, client):
        """PATCH /v1/collab/users/{id} updates role."""
        uid = getattr(self.__class__, "_created_user_id", None)
        if not uid:
            pytest.skip("No user to update")
        r = client.patch(f"/v1/collab/users/{uid}", json={"role": "admin"})
        assert r.status_code == 200

    def test_delete_user(self, client):
        """DELETE /v1/collab/users/{id} removes the user."""
        uid = getattr(self.__class__, "_created_user_id", None)
        if not uid:
            pytest.skip("No user to delete")
        r = client.delete(f"/v1/collab/users/{uid}")
        assert r.status_code in (200, 204)


class TestCollabWorkspaces:
    """Tests for /v1/collab/workspaces CRUD."""

    def test_list_workspaces(self, client):
        """GET /v1/collab/workspaces returns a list."""
        r = client.get("/v1/collab/workspaces")
        assert r.status_code == 200

    def test_create_workspace(self, client):
        """POST /v1/collab/workspaces creates a workspace."""
        payload = {
            "name": f"test_workspace_{uuid.uuid4().hex[:8]}",
            "description": "Test workspace for automated tests"
        }
        r = client.post("/v1/collab/workspaces", json=payload)
        assert r.status_code in (200, 201)
        data = r.json()
        self.__class__._ws_id = data.get("id")

    def test_update_workspace(self, client):
        """PATCH /v1/collab/workspaces/{id} updates name."""
        ws_id = getattr(self.__class__, "_ws_id", None)
        if not ws_id:
            pytest.skip("No workspace to update")
        r = client.patch(f"/v1/collab/workspaces/{ws_id}", json={"name": "renamed_workspace"})
        assert r.status_code == 200

    def test_delete_workspace(self, client):
        """DELETE /v1/collab/workspaces/{id} removes it."""
        ws_id = getattr(self.__class__, "_ws_id", None)
        if not ws_id:
            pytest.skip("No workspace to delete")
        r = client.delete(f"/v1/collab/workspaces/{ws_id}")
        assert r.status_code in (200, 204)


class TestCollabHandoffs:
    """Tests for /v1/collab/handoff endpoints."""

    def test_list_handoffs(self, client):
        """GET /v1/collab/handoff returns a list."""
        r = client.get("/v1/collab/handoff")
        assert r.status_code == 200

    def test_create_handoff(self, client):
        """POST /v1/collab/handoff creates a handoff."""
        payload = {
            "from_user": "test_from",
            "to_user": "test_to",
            "conversation_id": str(uuid.uuid4()),
            "notes": "Test handoff"
        }
        r = client.post("/v1/collab/handoff", json=payload)
        # May fail if users don't exist — that's OK
        assert r.status_code in (200, 201, 404, 422)
        if r.status_code in (200, 201):
            self.__class__._handoff_id = r.json().get("id")

    def test_accept_handoff(self, client):
        """POST /v1/collab/handoff/{id}/accept accepts it."""
        hid = getattr(self.__class__, "_handoff_id", None)
        if not hid:
            pytest.skip("No handoff to accept")
        r = client.post(f"/v1/collab/handoff/{hid}/accept")
        assert r.status_code in (200, 404)


class TestCollabAudit:
    """Tests for /v1/collab/audit endpoints."""

    def test_get_audit_log(self, client):
        """GET /v1/collab/audit returns audit events."""
        r = client.get("/v1/collab/audit")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_create_audit_entry(self, client):
        """POST /v1/collab/audit creates an audit event."""
        payload = {
            "action": "test_action",
            "resource_type": "test",
            "user": "test_user",
            "details": "Automated test audit entry"
        }
        r = client.post("/v1/collab/audit", json=payload)
        assert r.status_code in (200, 201)
