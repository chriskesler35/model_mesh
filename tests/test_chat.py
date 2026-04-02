"""
test_chat.py - Tests for /v1/chat/completions endpoint.

These tests call real LLMs — marked as @pytest.mark.slow.
Skip with: pytest -m "not slow"
"""

import pytest


@pytest.mark.slow
class TestChatCompletions:
    """Tests for the chat completion endpoint."""

    def test_chat_completions_basic(self, client):
        """POST /v1/chat/completions with a simple message (non-streaming)."""
        payload = {
            "messages": [
                {"role": "user", "content": "Say hello in exactly 3 words."}
            ],
            "model": "Default",
            "stream": False
        }
        r = client.post("/v1/chat/completions", json=payload, timeout=60.0)
        assert r.status_code == 200
        data = r.json()
        # Should have content in response
        content = data.get("content") or data.get("choices", [{}])[0].get("message", {}).get("content", "")
        assert len(content) > 0

    def test_chat_completions_with_model_override(self, client):
        """POST /v1/chat/completions with explicit model."""
        payload = {
            "messages": [
                {"role": "user", "content": "Reply with the word 'test' only."}
            ],
            "model": "ollama/llama3.1:8b"
        }
        r = client.post("/v1/chat/completions", json=payload, timeout=60.0)
        # May fail if model not available
        assert r.status_code in (200, 400, 404, 503)

    def test_chat_completions_empty_messages(self, client):
        """POST /v1/chat/completions with empty messages should fail."""
        payload = {"messages": []}
        r = client.post("/v1/chat/completions", json=payload)
        assert r.status_code in (400, 422)

    def test_chat_completions_no_body(self, client):
        """POST /v1/chat/completions with no body should return 422."""
        r = client.post("/v1/chat/completions")
        assert r.status_code == 422

    def test_chat_completions_system_message(self, client):
        """POST /v1/chat/completions with system + user messages (non-streaming)."""
        payload = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Always respond in uppercase."},
                {"role": "user", "content": "Say hi."}
            ],
            "model": "Default",
            "stream": False
        }
        r = client.post("/v1/chat/completions", json=payload, timeout=60.0)
        assert r.status_code == 200

    def test_chat_completions_multi_turn(self, client):
        """POST /v1/chat/completions with multi-turn conversation (non-streaming)."""
        payload = {
            "messages": [
                {"role": "user", "content": "My name is TestBot."},
                {"role": "assistant", "content": "Hello TestBot!"},
                {"role": "user", "content": "What is my name?"}
            ],
            "model": "Default",
            "stream": False
        }
        r = client.post("/v1/chat/completions", json=payload, timeout=60.0)
        assert r.status_code == 200
