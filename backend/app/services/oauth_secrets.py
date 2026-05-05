"""Encrypted OAuth token persistence helpers."""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.oauth_credential import OAuthCredential

logger = logging.getLogger(__name__)


def _encryption_secret() -> str:
    return (settings.oauth_token_encryption_key or settings.jwt_secret or "").strip()


def _try_get_fernet():
    secret = _encryption_secret()
    if not secret:
        return None
    try:
        from cryptography.fernet import Fernet  # type: ignore

        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        return Fernet(key)
    except Exception:
        return None


def encrypt_token(token: str) -> str:
    value = (token or "").strip()
    if not value:
        return ""
    fernet = _try_get_fernet()
    if not fernet:
        logger.warning("Token encryption unavailable (cryptography missing). Storing legacy plaintext wrapper.")
        return "plain:" + value
    encrypted = fernet.encrypt(value.encode("utf-8"))
    return "enc:" + encrypted.decode("utf-8")


def decrypt_token(ciphertext: str) -> Optional[str]:
    value = (ciphertext or "").strip()
    if not value:
        return None
    if value.startswith("plain:"):
        return value[6:]
    if value.startswith("enc:"):
        payload = value[4:]
        fernet = _try_get_fernet()
        if not fernet:
            logger.warning("Cannot decrypt OAuth token because encryption backend is unavailable.")
            return None
        try:
            return fernet.decrypt(payload.encode("utf-8")).decode("utf-8")
        except Exception:
            return None
    # Backward-compatible: unknown format treated as plaintext legacy data.
    return value


async def upsert_user_oauth_token(user_id: str, provider: str, token: str) -> None:
    uid = (user_id or "").strip()
    prov = (provider or "").strip().lower()
    if not uid or not prov or not (token or "").strip():
        return

    encrypted = encrypt_token(token)
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(OAuthCredential).where(
                    OAuthCredential.user_id == uid,
                    OAuthCredential.provider == prov,
                )
            )
        ).scalar_one_or_none()
        if row:
            row.access_token_encrypted = encrypted
        else:
            db.add(
                OAuthCredential(
                    user_id=uid,
                    provider=prov,
                    access_token_encrypted=encrypted,
                )
            )
        await db.commit()


async def get_user_oauth_token(user_id: str, provider: str) -> Optional[str]:
    uid = (user_id or "").strip()
    prov = (provider or "").strip().lower()
    if not uid or not prov:
        return None

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(OAuthCredential).where(
                    OAuthCredential.user_id == uid,
                    OAuthCredential.provider == prov,
                )
            )
        ).scalar_one_or_none()
        if not row:
            return None
        return decrypt_token(row.access_token_encrypted)


async def get_any_provider_token_from_db(provider: str) -> Optional[str]:
    """Return the first available decrypted token for a provider (any user).

    Used when the caller has no specific user_id context — e.g. picking a
    GitHub Copilot token to make API calls on behalf of the system.
    """
    prov = (provider or "").strip().lower()
    if not prov:
        return None

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(OAuthCredential)
                .where(OAuthCredential.provider == prov)
                .limit(1)
            )
        ).scalar_one_or_none()
        if not row:
            return None
        return decrypt_token(row.access_token_encrypted)


async def backfill_tokens_from_json() -> int:
    """One-time migration: read github tokens from collab_users.json → DB.

    Idempotent — skips users that already have a DB entry for the provider.
    Returns the count of tokens newly written.
    """
    import json
    from pathlib import Path

    users_file = Path(__file__).parent.parent.parent.parent / "data" / "collab_users.json"
    if not users_file.exists():
        return 0

    try:
        users = json.loads(users_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("backfill_tokens_from_json: cannot read users file: %s", exc)
        return 0

    if isinstance(users, list):
        users_dict = {u.get("id", str(i)): u for i, u in enumerate(users) if isinstance(u, dict)}
    elif isinstance(users, dict):
        users_dict = users
    else:
        return 0

    written = 0
    async with AsyncSessionLocal() as db:
        for uid, user in users_dict.items():
            if not isinstance(user, dict):
                continue
            token = (user.get("github_token") or "").strip()
            if not token:
                continue
            # Check for an existing DB row before writing
            existing = (
                await db.execute(
                    select(OAuthCredential).where(
                        OAuthCredential.user_id == uid,
                        OAuthCredential.provider == "github",
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue
            db.add(
                OAuthCredential(
                    user_id=uid,
                    provider="github",
                    access_token_encrypted=encrypt_token(token),
                )
            )
            written += 1
        if written:
            await db.commit()

    if written:
        logger.info("backfill_tokens_from_json: migrated %d github token(s) to DB", written)
    return written
