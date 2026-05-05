"""Application configuration using Pydantic Settings."""

import logging
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database - use SQLite file for local dev, Postgres for production
    database_url: str = ""
    
    # Redis - optional for local dev
    redis_url: Optional[str] = None
    
    # API Keys (from environment, never stored in DB)
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # GitHub OAuth (register an app at https://github.com/settings/developers)
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    github_oauth_redirect_url: str = "http://localhost:3001/auth/github/callback"

    # Google OAuth (register at https://console.cloud.google.com/apis/credentials)
    google_oauth_client_id: Optional[str] = None
    google_oauth_client_secret: Optional[str] = None
    google_oauth_redirect_url: str = "http://localhost:3001/auth/google/callback"
    
    # Telegram bot
    telegram_bot_token: Optional[str] = None
    telegram_chat_ids: Optional[str] = None  # comma-separated list of authorized chat IDs

    # ComfyUI for image generation
    comfyui_url: str = "http://localhost:8188"
    
    # Application
    app_env: str = "development"
    modelmesh_api_key: str = "modelmesh_local_dev_key"
    ollama_base_url: str = "http://localhost:11434"
    model_routing_auto_enabled: bool = False

    # JWT auth (multi-user collaboration)
    jwt_secret: str = "change-me-in-production-this-is-not-secure"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24 * 7  # 7-day tokens for LAN/Tailscale use

    # OAuth token encryption (optional override; falls back to JWT secret)
    oauth_token_encryption_key: Optional[str] = None
    
    # Memory
    memory_ttl_seconds: int = 86400  # 24 hours
    default_max_memory_messages: int = 10

    # Rate Limiting (requests per minute/hour)
    rate_limit_rpm: int = 60  # 60 requests per minute
    rate_limit_rph: int = 1000  # 1000 requests per hour

    # Feature flags (staged rollout)
    ui_guided_mode: bool = True
    method_launcher_v1: bool = False
    skills_marketplace_alpha: bool = False
    
    class Config:
        env_file = [".env", "../.env"]
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set default database URL if not provided
        if not self.database_url:
            # Use SQLite file in the project directory for persistence
            db_path = Path(__file__).parent.parent.parent / "data" / "devforgeai.db"
            db_path.parent.mkdir(exist_ok=True)
            self.database_url = f"sqlite+aiosqlite:///{db_path}"
        self._validate_security_defaults()

    def _validate_security_defaults(self) -> None:
        """Guard against insecure default credentials in non-dev environments."""
        env = (self.app_env or os.environ.get("APP_ENV") or os.environ.get("ENV") or "development").lower()
        non_dev = env not in {"dev", "development", "local", "test", "testing"}

        default_jwt = "change-me-in-production-this-is-not-secure"
        default_owner_key = "modelmesh_local_dev_key"

        if self.jwt_secret == default_jwt:
            if non_dev:
                raise ValueError(
                    "JWT_SECRET is using the insecure default value. "
                    "Set a strong JWT_SECRET before starting in non-development environments."
                )
            logger.warning("JWT_SECRET is using the default development value.")

        if self.modelmesh_api_key == default_owner_key:
            logger.warning("MODELMESH_API_KEY is using the default development value.")


settings = Settings()