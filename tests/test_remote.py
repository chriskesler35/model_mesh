"""
test_remote.py - Tests for /v1/remote/*, /v1/telegram/* endpoints.

Covers: remote health, sessions, Tailscale info, Telegram bot.
"""

import asyncio
import pytest
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


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

    def test_network_profiles(self, client):
        """GET /v1/remote/network-profiles returns both Tailscale and WireGuard profiles."""
        r = client.get("/v1/remote/network-profiles")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

        profiles = data.get("profiles")
        assert isinstance(profiles, dict)
        assert "tailscale" in profiles
        assert "wireguard" in profiles

        for key in ("tailscale", "wireguard"):
            profile = profiles[key]
            assert isinstance(profile, dict)
            assert profile.get("network") == key
            assert "detected_ip" in profile
            assert "connected" in profile
            assert "frontend_url" in profile
            assert "backend_url" in profile
            assert "configured_frontend_url" in profile
            assert "configured_backend_url" in profile


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

    def test_extract_image_attachment_prefers_largest_photo(self):
        """Telegram photo messages should produce a usable attachment payload."""
        from app.routes import telegram_bot

        attachment = telegram_bot._extract_image_attachment({
            "photo": [
                {"file_id": "small", "file_size": 12, "file_unique_id": "u1"},
                {"file_id": "large", "file_size": 48, "file_unique_id": "u2"},
            ]
        })

        assert attachment is not None
        assert attachment["file_id"] == "large"
        assert attachment["mime_type"] == "image/jpeg"

    def test_extract_image_attachment_accepts_image_document_only(self):
        """Telegram image documents should be treated as image inputs too."""
        from app.routes import telegram_bot

        attachment = telegram_bot._extract_image_attachment({
            "document": {
                "file_id": "doc-file",
                "file_name": "source.png",
                "mime_type": "image/png",
                "file_size": 2048,
            }
        })

        assert attachment is not None
        assert attachment["file_id"] == "doc-file"
        assert attachment["filename"] == "source.png"
        assert attachment["mime_type"] == "image/png"

    def test_plain_text_after_uploaded_image_routes_to_reimagine(self, monkeypatch):
        """A plain follow-up message should edit the last Telegram image instead of becoming chat text."""
        from app.routes import telegram_bot

        telegram_bot._telegram_pending_images.clear()
        telegram_bot._telegram_pending_images[321] = {"source_image_id": "img-123"}
        calls = {}

        async def fake_handle_image_command(chat_id, args, source_image_id=None):
            calls["chat_id"] = chat_id
            calls["args"] = args
            calls["source_image_id"] = source_image_id

        monkeypatch.setattr(telegram_bot, "handle_image_command", fake_handle_image_command)

        asyncio.run(telegram_bot.process_telegram_command(321, "make it cinematic"))

        assert calls == {
            "chat_id": 321,
            "args": "make it cinematic",
            "source_image_id": None,
        }
        telegram_bot._telegram_pending_images.clear()

    def test_media_message_with_caption_uploads_and_reimagines(self, monkeypatch):
        """Inbound Telegram images with captions should upload and trigger image editing."""
        from app.routes import telegram_bot

        telegram_bot._telegram_pending_images.clear()
        events = {}

        async def fake_download(file_id, fallback_name="telegram-image"):
            events["download"] = {"file_id": file_id, "fallback_name": fallback_name}
            return {
                "bytes": b"fake-image-bytes",
                "mime_type": "image/jpeg",
                "filename": "telegram-photo.jpg",
            }

        async def fake_upload(image_bytes, mime_type, filename):
            events["upload"] = {
                "image_bytes": image_bytes,
                "mime_type": mime_type,
                "filename": filename,
            }
            return {"id": "uploaded-image-id"}

        async def fake_handle_image_command(chat_id, args, source_image_id=None):
            events["handle"] = {
                "chat_id": chat_id,
                "args": args,
                "source_image_id": source_image_id,
            }

        async def fake_send_message(chat_id, text, parse_mode="Markdown"):
            events.setdefault("messages", []).append({"chat_id": chat_id, "text": text})
            return {"ok": True}

        monkeypatch.setattr(telegram_bot, "_download_telegram_file", fake_download)
        monkeypatch.setattr(telegram_bot, "_upload_image_to_devforge", fake_upload)
        monkeypatch.setattr(telegram_bot, "handle_image_command", fake_handle_image_command)
        monkeypatch.setattr(telegram_bot, "send_telegram_message", fake_send_message)

        message = {
            "chat": {"id": 555},
            "caption": "/image make it watercolor",
            "photo": [
                {"file_id": "telegram-photo-file", "file_size": 300, "file_unique_id": "unique-photo"}
            ],
        }

        asyncio.run(telegram_bot.process_telegram_media_message(555, message))

        assert events["download"]["file_id"] == "telegram-photo-file"
        assert events["upload"]["mime_type"] == "image/jpeg"
        assert events["handle"] == {
            "chat_id": 555,
            "args": "make it watercolor",
            "source_image_id": "uploaded-image-id",
        }
        assert telegram_bot._telegram_pending_images[555]["source_image_id"] == "uploaded-image-id"
        telegram_bot._telegram_pending_images.clear()
