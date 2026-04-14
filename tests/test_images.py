"""
test_images.py - Tests for image gallery and generation endpoints.

Covers:
  GET    /v1/images/
  POST   /v1/images/generations   (skipped if no provider)
  GET    /v1/images/{id}
  GET    /v1/images/{id}/download
  DELETE /v1/images/{id}
  POST   /v1/images/{id}/variations
  POST   /v1/images/upload
  POST   /v1/images/edit
"""

import uuid
import pytest


def _upload_test_image(client) -> str | None:
    """Helper: upload a tiny 1x1 PNG to get a real image id. Returns id or None."""
    import base64
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r = client.post("/v1/images/upload", json={
        "base64": base64.b64encode(png_bytes).decode(),
        "filename": f"pytest-upload-{uuid.uuid4().hex[:8]}.png",
        "mime_type": "image/png"
    })
    if r.status_code in (200, 201):
        data = r.json()
        return data.get("id") or data.get("image", {}).get("id")
    return None


class TestListImages:
    def test_list_images_returns_200(self, client):
        """GET /v1/images/ should return 200."""
        r = client.get("/v1/images/")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_images_returns_list_or_dict(self, client):
        """GET /v1/images/ should return a JSON list or object."""
        r = client.get("/v1/images/")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


class TestImageUpload:
    def test_upload_image_returns_success(self, client):
        """POST /v1/images/upload with a valid PNG should return 200 or 201."""
        import base64
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        r = client.post("/v1/images/upload", json={
            "base64": base64.b64encode(png_bytes).decode(),
            "filename": f"pytest-{uuid.uuid4().hex[:8]}.png",
            "mime_type": "image/png"
        })
        assert r.status_code in (200, 201, 422), f"Unexpected: {r.status_code}: {r.text}"
        if r.status_code in (200, 201):
            data = r.json()
            img_id = data.get("id") or data.get("image", {}).get("id")
            if img_id:
                client.delete(f"/v1/images/{img_id}")

    def test_upload_no_file_returns_422(self, client):
        """POST /v1/images/upload without a file should return 422."""
        r = client.post("/v1/images/upload", data={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


class TestImageByID:
    @pytest.fixture(autouse=True)
    def setup_image(self, client):
        """Upload a test image and delete it after the test."""
        self.img_id = _upload_test_image(client)
        yield
        if self.img_id:
            client.delete(f"/v1/images/{self.img_id}")

    def test_get_image_by_id(self, client):
        """GET /v1/images/{id} should return the image record."""
        if not self.img_id:
            pytest.skip("Image upload not available")
        r = client.get(f"/v1/images/{self.img_id}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_get_image_404_for_nonexistent(self, client):
        """GET /v1/images/{id} with bogus id should return 404."""
        r = client.get("/v1/images/nonexistent-fake-id-99999")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_download_image(self, client):
        """GET /v1/images/{id}/download should return the image binary."""
        if not self.img_id:
            pytest.skip("Image upload not available")
        r = client.get(f"/v1/images/{self.img_id}/download")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        assert len(r.content) > 0

    def test_download_nonexistent_image_returns_404(self, client):
        """GET /v1/images/{id}/download with bogus id should return 404."""
        r = client.get("/v1/images/nonexistent-fake-id-99999/download")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_delete_image_returns_success(self, client):
        """DELETE /v1/images/{id} should return 200 or 204."""
        if not self.img_id:
            pytest.skip("Image upload not available")
        r = client.delete(f"/v1/images/{self.img_id}")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"
        self.img_id = None

    def test_delete_nonexistent_image_returns_404(self, client):
        """DELETE /v1/images/{id} with bogus id should return 404."""
        r = client.delete("/v1/images/nonexistent-fake-id-99999")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


class TestImageVariations:
    def test_variations_nonexistent_image_returns_404(self, client):
        """POST /v1/images/{id}/variations with bogus id should return 404."""
        r = client.post("/v1/images/nonexistent-fake-id-99999/variations", json={})
        assert r.status_code in (404, 422), f"Expected 404/422, got {r.status_code}: {r.text}"

    def test_variations_comfyui_rejects_non_png_source(self, client):
        """ComfyUI variations should reject JPG uploads with a clear message."""
        import base64

        jpeg_bytes = base64.b64decode(
            "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxAQEBUQEBAVFRAQDw8PEA8PDw8QEA8QFREWFhURFRUYHSggGBolGxUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGhAQGi0fHyUtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMBEQACEQEDEQH/xAAXAAEBAQEAAAAAAAAAAAAAAAAAAQID/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEAMQAAAB6A//xAAXEAEBAQEAAAAAAAAAAAAAAAABEQAh/9oACAEBAAEFAm0a1//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8BP//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8BP//Z"
        )

        upload = client.post("/v1/images/upload", json={
            "base64": base64.b64encode(jpeg_bytes).decode(),
            "filename": "test.jpg",
            "mime_type": "image/jpeg",
        })
        assert upload.status_code == 200, upload.text
        img_id = upload.json()["id"]

        try:
            r = client.post(f"/v1/images/{img_id}/variations", json={"model": "comfyui-local"})
            assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
            assert "requires a PNG source image" in r.text
        finally:
            client.delete(f"/v1/images/{img_id}")

    @pytest.mark.slow
    def test_variations_with_real_image(self, client):
        """POST /v1/images/{id}/variations should return 200 or indicate no provider."""
        img_id = _upload_test_image(client)
        if not img_id:
            pytest.skip("Image upload not available")
        try:
            r = client.post(f"/v1/images/{img_id}/variations", json={})
            assert r.status_code in (200, 201, 400, 422, 503), f"Unexpected: {r.status_code}: {r.text}"
        finally:
            client.delete(f"/v1/images/{img_id}")


class TestImageGeneration:
    @pytest.mark.slow
    def test_generation_returns_success_or_no_provider(self, client):
        """POST /v1/images/generations should succeed or return 422/503 if no provider."""
        payload = {
            "prompt": "A simple blue circle on white background",
            "n": 1,
            "size": "256x256",
        }
        r = client.post("/v1/images/generations", json=payload)
        assert r.status_code in (200, 201, 422, 503), f"Unexpected: {r.status_code}: {r.text}"

    def test_generation_missing_prompt_returns_422(self, client):
        """POST /v1/images/generations without a prompt should return 422."""
        r = client.post("/v1/images/generations", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


class TestImageEdit:
    def test_edit_no_file_returns_422(self, client):
        """POST /v1/images/edit without required fields should return 422."""
        r = client.post("/v1/images/edit", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"

    @pytest.mark.slow
    def test_edit_with_image_returns_result_or_no_provider(self, client):
        """POST /v1/images/edit with an image should return 200 or 422/503."""
        import base64
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        r = client.post("/v1/images/edit", json={
            "source_base64": base64.b64encode(png_bytes).decode(),
            "source_mime": "image/png",
            "prompt": "Make it red"
        })
        assert r.status_code in (200, 201, 400, 422, 503), f"Unexpected: {r.status_code}: {r.text}"
