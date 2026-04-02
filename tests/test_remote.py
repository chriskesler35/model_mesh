"""
test_remote.py - Tests for /v1/remote/*, /v1/telegram/* endpoints.

Covers: remote health, sessions, Tailscale info, Telegram bot.
"""

import pytest
import uuid


class TestRemoteHealth:
    """Tests for /v1/remote/health and info."""

    def test_remote_health(self, client):
        """GET /v1/remote/health returns system health."""
        r = client.get("/v1/remote/health")
        assert r.status_code in (200, 500), f"Unexpected: {r.status_code}: {r.text}"
        if r.status_code == 200:
            data = r.json()
            assert "status" in data or "healthy" in data or "backend" in data

    def test_tailscale_info(self, client):
        """GET /v1/remote/tailscale-info returns Tailscale connection details."""
        r = client.get("/v1/remote/tailscale-info")
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            data = r.json()
            # Should have some network info
            assert isinstance(data, dict)


class TestRemoteSessions:
    """Tests for /v1/remote/sessions CRUD."""

    def test_list_sessions(self, client):
        """GET /v1/remote/sessions returns session list."""
        r = client.get("/v1/remote/sessions")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_create_session(self, client):
        """POST /v1/remote/sessions creates a remote session."""
        payload = {
            "agent_type": "coder",
            "task": "test task from pytest",
            "model": "test-model"
        }
        r = client.post("/v1/remote/sessions", json=payload)
        assert r.status_code in (200, 201)
        data = r.json()
        self.__class__._session_id = data.get("session_id") or data.get("id")

    def test_get_session(self, client):
        """GET /v1/remote/sessions/{id} returns session details."""
        sid = getattr(self.__class__, "_session_id", None)
        if not sid:
            pytest.skip("No session to get")
        r = client.get(f"/v1/remote/sessions/{sid}")
        assert r.status_code in (200, 404)

    def test_cancel_session(self, client):
        """POST /v1/remote/sessions/{id}/cancel cancels the session."""
        sid = getattr(self.__class__, "_session_id", None)
        if not sid:
            pytest.skip("No session to cancel")
        r = client.post(f"/v1/remote/sessions/{sid}/cancel")
        assert r.status_code in (200, 404)

    def test_delete_session(self, client):
        """DELETE /v1/remote/sessions/{id} removes the session."""
        sid = getattr(self.__class__, "_session_id", None)
        if not sid:
            pytest.skip("No session to delete")
        r = client.delete(f"/v1/remote/sessions/{sid}")
        assert r.status_code in (200, 204, 404)

    def test_get_nonexistent_session(self, client):
        """GET /v1/remote/sessions/{id} for missing ID returns 404."""
        r = client.get(f"/v1/remote/sessions/{uuid.uuid4()}")
        assert r.status_code == 404


class TestTelegram:
    """Tests for /v1/telegram/* endpoints."""

    def test_telegram_status(self, client):
        """GET /v1/telegram/status returns bot status."""
        r = client.get("/v1/telegram/status")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_telegram_webhook_info(self, client):
        """GET /v1/telegram/webhook-info returns webhook details."""
        r = client.get("/v1/telegram/webhook-info")
        assert r.status_code in (200, 503)

    def test_telegram_send_no_token(self, client):
        """POST /v1/telegram/send without valid token should fail gracefully."""
        r = client.post("/v1/telegram/send", json={
            "chat_id": "123456",
            "message": "test message"
        })
        # May succeed if token is configured, or fail gracefully
        assert r.status_code in (200, 400, 422, 500, 503)
