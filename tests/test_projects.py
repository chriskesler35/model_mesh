"""
test_projects.py - Tests for project management endpoints.

Covers:
  GET    /v1/projects/templates
  GET    /v1/projects/
  POST   /v1/projects/
  GET    /v1/projects/{id}
  PATCH  /v1/projects/{id}
  DELETE /v1/projects/{id}
  GET    /v1/projects/{id}/files
  GET    /v1/projects/{id}/files/read
  GET    /v1/projects/{id}/sandbox
  POST   /v1/projects/{id}/sandbox
"""

import uuid
import pytest


class TestProjectTemplates:
    def test_list_templates_returns_200(self, client):
        """GET /v1/projects/templates should return 200."""
        r = client.get("/v1/projects/templates")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_templates_returns_list_or_dict(self, client):
        """GET /v1/projects/templates should return a JSON list or object."""
        r = client.get("/v1/projects/templates")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


class TestListProjects:
    def test_list_projects_returns_200(self, client):
        """GET /v1/projects/ should return 200."""
        r = client.get("/v1/projects/")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_projects_returns_list_or_dict(self, client):
        """GET /v1/projects/ should return a JSON list or object."""
        r = client.get("/v1/projects/")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


class TestProjectCRUD:
    @pytest.fixture(autouse=True)
    def setup_project(self, client):
        """Create a test project and clean it up after each test."""
        payload = {
            "name": f"TestProject-{uuid.uuid4().hex[:8]}",
            "description": "A test project created by pytest",
            "template": "blank",
            "path": f"C:/tmp/devforge-test-{uuid.uuid4().hex[:8]}",
        }
        r = client.post("/v1/projects/", json=payload)
        assert r.status_code in (200, 201), f"Setup failed: {r.status_code} {r.text}"
        self.project = r.json()
        self.project_id = self.project.get("id") or self.project.get("project", {}).get("id")
        yield
        if self.project_id:
            client.delete(f"/v1/projects/{self.project_id}")

    def test_create_project_has_id(self, client):
        """POST /v1/projects/ should return the created project with an id."""
        assert self.project_id is not None, "Created project has no id"

    def test_get_project_by_id(self, client):
        """GET /v1/projects/{id} should return the project we created."""
        r = client.get(f"/v1/projects/{self.project_id}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        proj_data = data.get("project", data)
        assert str(proj_data.get("id")) == str(self.project_id)

    def test_get_project_404_for_nonexistent(self, client):
        """GET /v1/projects/{id} with bogus id should return 404."""
        r = client.get("/v1/projects/nonexistent-fake-id-99999")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_update_project_description(self, client):
        """PATCH /v1/projects/{id} should update the project's description."""
        r = client.patch(
            f"/v1/projects/{self.project_id}",
            json={"description": "Updated by pytest"}
        )
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"

    def test_update_nonexistent_project_returns_404(self, client):
        """PATCH /v1/projects/{id} with bogus id should return 404."""
        r = client.patch("/v1/projects/nonexistent-fake-id-99999", json={"description": "x"})
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_delete_project_returns_success(self, client):
        """DELETE /v1/projects/{id} should return 200 or 204."""
        r = client.delete(f"/v1/projects/{self.project_id}")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"
        self.project_id = None

    def test_delete_nonexistent_project_returns_404(self, client):
        """DELETE /v1/projects/{id} with bogus id should return 404."""
        r = client.delete("/v1/projects/nonexistent-fake-id-99999")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


class TestProjectFiles:
    @pytest.fixture(autouse=True)
    def setup_project(self, client):
        """Create a test project for file listing tests."""
        r = client.post("/v1/projects/", json={
            "name": f"FileTest-{uuid.uuid4().hex[:8]}",
            "description": "File listing test",
            "path": f"C:/tmp/devforge-test-{uuid.uuid4().hex[:8]}",
        })
        assert r.status_code in (200, 201), f"Setup failed: {r.status_code} {r.text}"
        data = r.json()
        self.project_id = data.get("id") or data.get("project", {}).get("id")
        yield
        if self.project_id:
            client.delete(f"/v1/projects/{self.project_id}")

    def test_list_project_files_returns_200_or_404(self, client):
        """GET /v1/projects/{id}/files should return 200 or 404 if project has no files."""
        r = client.get(f"/v1/projects/{self.project_id}/files")
        assert r.status_code in (200, 404), f"Expected 200/404, got {r.status_code}: {r.text}"

    def test_read_project_file_nonexistent_returns_404(self, client):
        """GET /v1/projects/{id}/files/read for non-existent file should return 404."""
        r = client.get(
            f"/v1/projects/{self.project_id}/files/read",
            params={"path": "nonexistent_file.txt"}
        )
        assert r.status_code in (404, 422), f"Expected 404/422, got {r.status_code}: {r.text}"

    def test_list_files_404_for_nonexistent_project(self, client):
        """GET /v1/projects/{id}/files with bogus project id should return 404."""
        r = client.get("/v1/projects/nonexistent-fake-id-99999/files")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


class TestProjectSandbox:
    @pytest.fixture(autouse=True)
    def setup_project(self, client):
        """Create a test project for sandbox tests."""
        r = client.post("/v1/projects/", json={
            "name": f"SandboxTest-{uuid.uuid4().hex[:8]}",
            "description": "Sandbox test",
            "path": f"C:/tmp/devforge-test-{uuid.uuid4().hex[:8]}",
        })
        assert r.status_code in (200, 201), f"Setup failed: {r.status_code} {r.text}"
        data = r.json()
        self.project_id = data.get("id") or data.get("project", {}).get("id")
        yield
        if self.project_id:
            client.delete(f"/v1/projects/{self.project_id}")

    def test_get_sandbox_status_returns_200_or_404(self, client):
        """GET /v1/projects/{id}/sandbox should return 200 or 404."""
        r = client.get(f"/v1/projects/{self.project_id}/sandbox")
        assert r.status_code in (200, 404), f"Expected 200/404, got {r.status_code}: {r.text}"

    @pytest.mark.destructive
    def test_post_sandbox_returns_success_or_error(self, client):
        """POST /v1/projects/{id}/sandbox should return a valid status."""
        r = client.post(f"/v1/projects/{self.project_id}/sandbox", json={})
        assert r.status_code in (200, 201, 400, 404, 422), (
            f"Unexpected: {r.status_code}: {r.text}"
        )
