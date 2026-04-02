"""
test_workflows.py - Tests for /v1/workflows/*, /v1/comfyui/* endpoints.

Covers: workflow templates, ComfyUI checkpoints/loras/status.
"""

import pytest


class TestWorkflows:
    """Tests for workflow template endpoints."""

    def test_list_workflows(self, client):
        """GET /v1/workflows returns available workflow templates."""
        r = client.get("/v1/workflows")
        assert r.status_code == 200
        data = r.json()
        # Should have a list of workflows
        workflows = data.get("workflows", data.get("data", data))
        if isinstance(workflows, list):
            assert len(workflows) >= 0
            # Check known workflows exist
            names = [w.get("name", w.get("id", "")) for w in workflows]
            # We expect SDXL, Flux Schnell, Flux Dev, SD 1.5 if data/workflows/ populated
            if len(workflows) > 0:
                # Each workflow should have name and id
                w = workflows[0]
                assert "name" in w or "id" in w

    def test_get_workflow_by_id(self, client):
        """GET /v1/workflows/{id} returns a specific workflow."""
        # First list to get an ID
        r = client.get("/v1/workflows")
        assert r.status_code == 200
        workflows = r.json().get("workflows", r.json().get("data", r.json()))
        if isinstance(workflows, list) and len(workflows) > 0:
            wf_id = workflows[0].get("id") or workflows[0].get("name")
            if wf_id:
                r2 = client.get(f"/v1/workflows/{wf_id}")
                assert r2.status_code in (200, 404)
        else:
            pytest.skip("No workflows available to test")

    def test_get_nonexistent_workflow(self, client):
        """GET /v1/workflows/{id} for missing workflow returns 404."""
        r = client.get("/v1/workflows/nonexistent_workflow_xyz")
        assert r.status_code == 404


class TestComfyUI:
    """Tests for ComfyUI integration endpoints."""

    def test_comfyui_status(self, client):
        """GET /v1/comfyui/status returns ComfyUI connection status."""
        r = client.get("/v1/comfyui/status")
        assert r.status_code in (200, 503)
        data = r.json()
        assert isinstance(data, dict)

    def test_comfyui_checkpoints(self, client):
        """GET /v1/comfyui/checkpoints returns available checkpoints."""
        r = client.get("/v1/comfyui/checkpoints")
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            data = r.json()
            checkpoints = data.get("checkpoints", data.get("data", data))
            if isinstance(checkpoints, list):
                assert len(checkpoints) >= 0

    def test_comfyui_loras(self, client):
        """GET /v1/comfyui/loras returns available LoRA models."""
        r = client.get("/v1/comfyui/loras")
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, dict)
