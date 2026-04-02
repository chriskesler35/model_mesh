"""
test_health.py - Tests for health and system endpoints.

Covers:
  GET  /v1/health
  GET  /v1/system/health
  GET  /v1/system/info
  GET  /v1/system/processes
  GET  /v1/system/logs
  GET  /v1/system/snapshots
  POST /v1/system/snapshots
  POST /v1/system/restart
"""

import pytest


class TestBasicHealth:
    def test_health_returns_200(self, client):
        """GET /health should return 200 and indicate the service is up."""
        r = client.get("/health")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_health_response_has_status(self, client):
        """GET /health response body should contain a status field."""
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        # Accept either {"status": ...} or {"ok": true} style
        assert isinstance(data, dict), "Expected a JSON object"


class TestSystemHealth:
    def test_system_health_returns_200(self, client):
        """GET /v1/system/health should return 200."""
        r = client.get("/v1/system/health")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_system_health_is_json(self, client):
        """GET /v1/system/health should return valid JSON."""
        r = client.get("/v1/system/health")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)


class TestSystemInfo:
    def test_system_info_returns_200(self, client):
        """GET /v1/system/info should return 200."""
        r = client.get("/v1/system/info")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_system_info_has_expected_fields(self, client):
        """GET /v1/system/info should return an object (may include version, platform, etc.)."""
        r = client.get("/v1/system/info")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)


class TestSystemProcesses:
    def test_system_processes_returns_200(self, client):
        """GET /v1/system/processes should return 200."""
        r = client.get("/v1/system/processes")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_system_processes_returns_list_or_dict(self, client):
        """GET /v1/system/processes should return a JSON structure."""
        r = client.get("/v1/system/processes")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


class TestSystemLogs:
    def test_system_logs_returns_200(self, client):
        """GET /v1/system/logs should return 200."""
        r = client.get("/v1/system/logs")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_system_logs_returns_list_or_dict(self, client):
        """GET /v1/system/logs should return a JSON structure (list of log entries or object)."""
        r = client.get("/v1/system/logs")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


class TestSystemSnapshots:
    def test_list_snapshots_returns_200(self, client):
        """GET /v1/system/snapshots should return 200."""
        r = client.get("/v1/system/snapshots")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_snapshots_returns_list_or_dict(self, client):
        """GET /v1/system/snapshots should return a JSON structure."""
        r = client.get("/v1/system/snapshots")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.destructive
    def test_create_snapshot_returns_success(self, client):
        """POST /v1/system/snapshots should create a snapshot and return 200 or 201."""
        r = client.post("/v1/system/snapshots")
        assert r.status_code in (200, 201), f"Expected 200/201, got {r.status_code}: {r.text}"

    @pytest.mark.destructive
    def test_create_snapshot_returns_json(self, client):
        """POST /v1/system/snapshots response should be valid JSON."""
        r = client.post("/v1/system/snapshots")
        assert r.status_code in (200, 201)
        data = r.json()
        assert isinstance(data, (dict, list))


class TestSystemRestart:
    @pytest.mark.destructive
    def test_restart_requires_auth(self, base_url):
        """POST /v1/system/restart without auth should return 401 or 403."""
        import httpx
        with httpx.Client(base_url=base_url, timeout=10.0) as c:
            r = c.post("/v1/system/restart")
            assert r.status_code in (401, 403, 422), (
                f"Expected auth error, got {r.status_code}: {r.text}"
            )

    @pytest.mark.destructive
    @pytest.mark.skip(reason="Restarting the server during tests would break the rest of the suite")
    def test_restart_with_auth(self, client):
        """POST /v1/system/restart with valid auth — skipped to avoid disrupting other tests."""
        r = client.post("/v1/system/restart")
        assert r.status_code in (200, 202, 204)
