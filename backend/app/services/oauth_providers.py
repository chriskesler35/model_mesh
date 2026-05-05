"""
Generic OAuth provider framework.

Provides a base class for OAuth providers and a registry for easy addition
of new providers (Google, Microsoft, etc.).

Each provider implements:
  - get_auth_url() → build the redirect URL
  - exchange_code() → swap authorization code for access token
  - get_user_profile() → fetch standardised user profile

Registry is built from environment variables:
  {PROVIDER}_CLIENT_ID / {PROVIDER}_CLIENT_SECRET
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx
import logging

logger = logging.getLogger(__name__)


@dataclass
class OAuthUserProfile:
    """Standardized user profile returned by any OAuth provider."""

    provider: str
    provider_user_id: str
    username: str
    display_name: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    access_token: Optional[str] = None


class BaseOAuthProvider(ABC):
    """Abstract base class for OAuth providers."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    # ── Abstract properties every provider must define ────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'github', 'google')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name (e.g., 'GitHub', 'Google')."""
        ...

    @property
    @abstractmethod
    def auth_url(self) -> str:
        """OAuth authorization endpoint URL."""
        ...

    @property
    @abstractmethod
    def token_url(self) -> str:
        """OAuth token exchange endpoint URL."""
        ...

    @property
    @abstractmethod
    def scopes(self) -> list[str]:
        """Required OAuth scopes."""
        ...

    # ── Shared logic (overridable where providers diverge) ───────────────────

    def get_auth_url(self, state: Optional[str] = None) -> str:
        """Build the full authorization redirect URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "response_type": "code",
        }
        if state:
            params["state"] = state
        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> str:
        """Exchange authorization code for access token. Returns the token.

        Default implementation sends a form-encoded POST (works for GitHub,
        Google, Microsoft, etc.). Override if a provider needs something
        different.
        """
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                self.token_url,
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            data = resp.json()

        token = data.get("access_token")
        if not token:
            error = data.get("error_description", data.get("error", "unknown"))
            raise ValueError(f"OAuth token exchange failed: {error}")
        return token

    @abstractmethod
    async def get_user_profile(self, access_token: str) -> OAuthUserProfile:
        """Fetch user profile using the access token."""
        ...

    @property
    def is_configured(self) -> bool:
        """Check if provider has required credentials."""
        return bool(self.client_id and self.client_secret)


# ─── Concrete Providers ──────────────────────────────────────────────────────


class GitHubOAuthProvider(BaseOAuthProvider):
    """GitHub OAuth provider."""

    @property
    def name(self) -> str:
        return "github"

    @property
    def display_name(self) -> str:
        return "GitHub"

    @property
    def auth_url(self) -> str:
        return "https://github.com/login/oauth/authorize"

    @property
    def token_url(self) -> str:
        return "https://github.com/login/oauth/access_token"

    @property
    def scopes(self) -> list[str]:
        # repo scope lets git-push work via HTTPS — matches existing github_oauth.py
        # copilot scope allows /copilot_internal/v2/token exchange for full model catalog
        return ["read:user", "user:email", "repo", "copilot"]

    async def get_user_profile(self, access_token: str) -> OAuthUserProfile:
        """Fetch GitHub user profile, including verified primary email."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            # User profile
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                raise ValueError(f"GitHub /user request failed: {resp.status_code}")
            data = resp.json()

            # Email — may be null on profile; fetch from /user/emails
            email = data.get("email")
            if not email:
                emails_resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                if emails_resp.status_code == 200:
                    emails = emails_resp.json()
                    primary = next(
                        (e for e in emails if e.get("primary") and e.get("verified")),
                        None,
                    )
                    if primary:
                        email = primary.get("email")

        return OAuthUserProfile(
            provider="github",
            provider_user_id=str(data["id"]),
            username=data.get("login", ""),
            display_name=data.get("name") or data.get("login", ""),
            email=email,
            avatar_url=data.get("avatar_url"),
            access_token=access_token,
        )


class GoogleOAuthProvider(BaseOAuthProvider):
    """Google OAuth provider (ready to configure — just set env vars)."""

    @property
    def name(self) -> str:
        return "google"

    @property
    def display_name(self) -> str:
        return "Google"

    @property
    def auth_url(self) -> str:
        return "https://accounts.google.com/o/oauth2/v2/auth"

    @property
    def token_url(self) -> str:
        return "https://oauth2.googleapis.com/token"

    @property
    def scopes(self) -> list[str]:
        return ["openid", "email", "profile"]

    async def get_user_profile(self, access_token: str) -> OAuthUserProfile:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                raise ValueError(f"Google userinfo request failed: {resp.status_code}")
            data = resp.json()

        return OAuthUserProfile(
            provider="google",
            provider_user_id=data["id"],
            username=data.get("email", "").split("@")[0],
            display_name=data.get("name", ""),
            email=data.get("email"),
            avatar_url=data.get("picture"),
            access_token=access_token,
        )


# ─── Registry ────────────────────────────────────────────────────────────────


def build_provider_registry() -> dict[str, BaseOAuthProvider]:
    """Build provider registry from environment configuration.

    Only providers whose client_id AND client_secret are set are included.
    """
    from app.config import settings

    registry: dict[str, BaseOAuthProvider] = {}

    # GitHub
    gh = GitHubOAuthProvider(
        client_id=getattr(settings, "github_client_id", "") or "",
        client_secret=getattr(settings, "github_client_secret", "") or "",
        redirect_uri=(
            getattr(settings, "github_oauth_redirect_url", "")
            or "http://localhost:3001/auth/github/callback"
        ),
    )
    if gh.is_configured:
        registry["github"] = gh

    # Google
    google = GoogleOAuthProvider(
        client_id=getattr(settings, "google_oauth_client_id", "") or "",
        client_secret=getattr(settings, "google_oauth_client_secret", "") or "",
        redirect_uri=(
            getattr(settings, "google_oauth_redirect_url", "")
            or "http://localhost:3001/auth/google/callback"
        ),
    )
    if google.is_configured:
        registry["google"] = google

    logger.info(
        "OAuth provider registry built — configured providers: %s",
        list(registry.keys()) or "(none)",
    )
    return registry


# Singleton registry — lazily built on first access
OAUTH_PROVIDERS: dict[str, BaseOAuthProvider] = {}


def get_provider_registry() -> dict[str, BaseOAuthProvider]:
    """Return the singleton provider registry, building it on first call."""
    global OAUTH_PROVIDERS
    if not OAUTH_PROVIDERS:
        OAUTH_PROVIDERS = build_provider_registry()
    return OAUTH_PROVIDERS
