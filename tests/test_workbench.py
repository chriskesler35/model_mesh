"""
test_workbench.py - Tests for workbench session endpoints.

Covers:
  POST   /v1/workbench/sessions
  GET    /v1/workbench/sessions
  GET    /v1/workbench/sessions/{id}
  GET    /v1/workbench/sessions/{id}/stream   (SSE)
  POST   /v1/workbench/sessions/{id}/message
  POST   /v1/workbench/sessions/{id}/cancel
  DELETE /v1/workbench/sessions/{id}
"""

import uuid
import pytest


class TestListWorkbenchSessions:
    def test_list_sessions_returns_200(self, client):
        """GET /v1/workbench/sessions should return 200."""
        r = client.get("/v1/workbench/sessions")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_sessions_returns_list_or_dict(self, client):
        """GET /v1/workbench/sessions should return JSON."""
        r = client.get("/v1/workbench/sessions")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


class TestWorkbenchSessionCRUD:
    @pytest.fixture(autouse=True)
    def setup_session(self, client):
        """Create a workbench session and clean it up after each test."""
        payload = {
            "task": f"Test task from pytest {uuid.uuid4().hex[:8]}",
            "agent_type": "coder",
        }
        r = client.post("/v1/workbench/sessions", json=payload)
        assert r.status_code in (200, 201), f"Setup failed: {r.status_code} {r.text}"
        self.session = r.json()
        self.session_id = self.session.get("id") or self.session.get("session", {}).get("id")
        yield
        if self.session_id:
            client.delete(f"/v1/workbench/sessions/{self.session_id}")

    def test_create_session_has_id(self, client):
        """POST /v1/workbench/sessions should return the created session with an id."""
        assert self.session_id is not None, "Created session has no id"

    def test_get_session_by_id(self, client):
        """GET /v1/workbench/sessions/{id} should return the session we created."""
        r = client.get(f"/v1/workbench/sessions/{self.session_id}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_get_session_404_for_nonexistent(self, client):
        """GET /v1/workbench/sessions/{id} with bogus id should return 404."""
        r = client.get("/v1/workbench/sessions/nonexistent-fake-id-99999")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_send_message_returns_success_or_error(self, client):
        """POST /v1/workbench/sessions/{id}/message should accept a message."""
        r = client.post(
            f"/v1/workbench/sessions/{self.session_id}/message",
            json={"content": "Hello from pytest"}
        )
        # Could be 200, 202 (accepted), 400 (no agent configured), or 422
        assert r.status_code in (200, 201, 202, 400, 422), (
            f"Unexpected: {r.status_code}: {r.text}"
        )

    def test_cancel_session_returns_success_or_not_running(self, client):
        """POST /v1/workbench/sessions/{id}/cancel should return a valid status."""
        r = client.post(f"/v1/workbench/sessions/{self.session_id}/cancel")
        assert r.status_code in (200, 204, 400, 404), (
            f"Unexpected: {r.status_code}: {r.text}"
        )

    def test_delete_session_returns_success(self, client):
        """DELETE /v1/workbench/sessions/{id} should return 200 or 204."""
        r = client.delete(f"/v1/workbench/sessions/{self.session_id}")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"
        self.session_id = None

    def test_delete_nonexistent_session_returns_success_or_404(self, client):
        """DELETE /v1/workbench/sessions/{id} with bogus id should return 200 or 404."""
        r = client.delete("/v1/workbench/sessions/nonexistent-fake-id-99999")
        assert r.status_code in (200, 204, 404), f"Expected 200/204/404, got {r.status_code}: {r.text}"


class TestWorkbenchSessionStream:
    def test_stream_nonexistent_session_returns_404(self, client):
        """GET /v1/workbench/sessions/{id}/stream with bogus id should return 404."""
        r = client.get(
            "/v1/workbench/sessions/nonexistent-fake-id-99999/stream",
            headers={"Accept": "text/event-stream"}
        )
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_stream_valid_session_returns_sse_or_no_content(self, client):
        """GET /v1/workbench/sessions/{id}/stream should return SSE headers or 204."""
        # Create a fresh session
        r = client.post("/v1/workbench/sessions", json={"task": f"SSETest-{uuid.uuid4().hex[:8]}", "agent_type": "coder"})
        if r.status_code not in (200, 201):
            pytest.skip("Could not create session for SSE test")
        session_data = r.json()
        session_id = session_data.get("id") or session_data.get("session", {}).get("id")
        if not session_id:
            pytest.skip("No session id")

        try:
            # Use a short timeout — SSE streams don't end naturally
            import httpx
            with httpx.Client(base_url=client.base_url, headers=dict(client.headers), timeout=5.0) as c:
                try:
                    resp = c.get(
                        f"/v1/workbench/sessions/{session_id}/stream",
                        headers={"Accept": "text/event-stream"}
                    )
                    assert resp.status_code in (200, 204, 404), (
                        f"Unexpected: {resp.status_code}: {resp.text[:200]}"
                    )
                except httpx.TimeoutException:
                    # SSE stream kept open — that's actually correct behavior
                    pass
        finally:
            client.delete(f"/v1/workbench/sessions/{session_id}")
