"""
test_conversations.py - Tests for conversation and message endpoints.

Covers:
  GET    /v1/conversations
  POST   /v1/conversations
  GET    /v1/conversations/{id}
  PATCH  /v1/conversations/{id}
  DELETE /v1/conversations/{id}
  GET    /v1/conversations/{id}/messages
  POST   /v1/conversations/{id}/messages
  PATCH  /v1/conversations/messages/{id}/image
  GET    /v1/conversations/cleanup
"""

import uuid
import pytest


class TestListConversations:
    def test_list_conversations_returns_200(self, client):
        """GET /v1/conversations should return 200."""
        r = client.get("/v1/conversations")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_conversations_returns_list_or_dict(self, client):
        """GET /v1/conversations should return a JSON array or object."""
        r = client.get("/v1/conversations")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


class TestConversationCRUD:
    @pytest.fixture(autouse=True)
    def setup_conversation(self, client):
        """Create a test conversation and clean it up after the test."""
        payload = {
            "title": f"Test Conversation {uuid.uuid4().hex[:8]}",
        }
        r = client.post("/v1/conversations", json=payload)
        assert r.status_code in (200, 201), f"Setup failed: {r.status_code} {r.text}"
        self.conv = r.json()
        self.conv_id = self.conv.get("id") or self.conv.get("conversation", {}).get("id")
        yield
        if self.conv_id:
            client.delete(f"/v1/conversations/{self.conv_id}")

    def test_create_conversation_has_id(self, client):
        """POST /v1/conversations should return a conversation with an id."""
        assert self.conv_id is not None, "Created conversation has no id"

    def test_get_conversation_by_id(self, client):
        """GET /v1/conversations/{id} should return the conversation we created."""
        r = client.get(f"/v1/conversations/{self.conv_id}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        conv_data = data.get("conversation", data)
        assert str(conv_data.get("id")) == str(self.conv_id)

    def test_get_conversation_404_for_nonexistent(self, client):
        """GET /v1/conversations/{id} with a nonexistent id should return 404."""
        r = client.get("/v1/conversations/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_update_conversation_title(self, client):
        """PATCH /v1/conversations/{id} should update the conversation title."""
        r = client.patch(
            f"/v1/conversations/{self.conv_id}",
            json={"title": "Updated Title from pytest"}
        )
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"

    def test_update_nonexistent_conversation_returns_404(self, client):
        """PATCH /v1/conversations/{id} with bogus id should return 404."""
        r = client.patch("/v1/conversations/00000000-0000-0000-0000-000000000000", json={"title": "x"})
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_delete_conversation_returns_success(self, client):
        """DELETE /v1/conversations/{id} should return 200 or 204."""
        r = client.delete(f"/v1/conversations/{self.conv_id}")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"
        self.conv_id = None

    def test_delete_nonexistent_conversation_returns_404(self, client):
        """DELETE /v1/conversations/{id} with bogus id should return 404."""
        r = client.delete("/v1/conversations/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


class TestConversationMessages:
    @pytest.fixture(autouse=True)
    def setup_conversation(self, client):
        """Create a test conversation with a message for message tests."""
        r = client.post("/v1/conversations", json={"title": f"MsgTest-{uuid.uuid4().hex[:8]}"})
        assert r.status_code in (200, 201), f"Setup failed: {r.status_code} {r.text}"
        self.conv = r.json()
        self.conv_id = self.conv.get("id") or self.conv.get("conversation", {}).get("id")
        self.message_id = None
        yield
        if self.conv_id:
            client.delete(f"/v1/conversations/{self.conv_id}")

    def test_list_messages_returns_200(self, client):
        """GET /v1/conversations/{id}/messages should return 200."""
        r = client.get(f"/v1/conversations/{self.conv_id}/messages")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_list_messages_returns_list_or_dict(self, client):
        """GET /v1/conversations/{id}/messages should return a list or object."""
        r = client.get(f"/v1/conversations/{self.conv_id}/messages")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_list_messages_404_for_nonexistent_conversation(self, client):
        """GET /v1/conversations/{id}/messages with bogus id should return 404."""
        r = client.get("/v1/conversations/00000000-0000-0000-0000-000000000000/messages")
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"

    def test_create_message_returns_success(self, client):
        """POST /v1/conversations/{id}/messages should add a message."""
        payload = {
            "role": "user",
            "content": "Hello from pytest test suite",
        }
        r = client.post(f"/v1/conversations/{self.conv_id}/messages", json=payload)
        assert r.status_code in (200, 201), f"Expected 200/201, got {r.status_code}: {r.text}"
        data = r.json()
        msg_data = data.get("message", data)
        self.message_id = msg_data.get("id")
        assert self.message_id is not None

    def test_create_message_missing_content_returns_422(self, client):
        """POST /v1/conversations/{id}/messages without content should return 422."""
        r = client.post(f"/v1/conversations/{self.conv_id}/messages", json={})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


class TestMessageImageUpdate:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        """Create conversation and message for image update tests."""
        r = client.post("/v1/conversations", json={"title": f"ImgTest-{uuid.uuid4().hex[:8]}"})
        assert r.status_code in (200, 201)
        self.conv = r.json()
        self.conv_id = self.conv.get("id") or self.conv.get("conversation", {}).get("id")

        r2 = client.post(
            f"/v1/conversations/{self.conv_id}/messages",
            json={"role": "user", "content": "Test message for image update"}
        )
        assert r2.status_code in (200, 201)
        msg_data = r2.json()
        self.message_id = msg_data.get("id") or msg_data.get("message", {}).get("id")
        yield
        if self.conv_id:
            client.delete(f"/v1/conversations/{self.conv_id}")

    def test_update_message_image_returns_success_or_422(self, client):
        """PATCH /v1/conversations/messages/{id}/image should return 200 or 422."""
        if not self.message_id:
            pytest.skip("No message id available")
        r = client.patch(
            f"/v1/conversations/messages/{self.message_id}/image",
            json={"image_url": "https://example.com/test.png"}
        )
        assert r.status_code in (200, 204, 422), f"Unexpected: {r.status_code}: {r.text}"

    def test_update_nonexistent_message_image_returns_404(self, client):
        """PATCH /v1/conversations/messages/{id}/image with bogus id should return 400 or 404."""
        r = client.patch(
            "/v1/conversations/messages/nonexistent-fake-id-99999/image",
            json={"image_url": "https://example.com/test.png"}
        )
        assert r.status_code in (400, 404), f"Expected 400/404, got {r.status_code}: {r.text}"


class TestConversationCleanup:
    def test_cleanup_endpoint_returns_200_or_204(self, client):
        """GET /v1/conversations/cleanup should return 200 or 204."""
        r = client.get("/v1/conversations/cleanup")
        assert r.status_code in (200, 204), f"Expected 200/204, got {r.status_code}: {r.text}"
