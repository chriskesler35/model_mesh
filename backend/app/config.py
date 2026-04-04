"""Application configuration using Pydantic Settings."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


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
    
    # Telegram bot
    telegram_bot_token: Optional[str] = None
    telegram_chat_ids: Optional[str] = None  # comma-separated list of authorized chat IDs

    # ComfyUI for image generation
    comfyui_url: str = "http://localhost:8188"
    
    # Application
    modelmesh_api_key: str = "modelmesh_local_dev_key"
    ollama_base_url: str = "http://localhost:11434"

    # JWT auth (multi-user collaboration)
    jwt_secret: str = "change-me-in-production-this-is-not-secure"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24 * 7  # 7-day tokens for LAN/Tailscale use
    
    # Memory
    memory_ttl_seconds: int = 86400  # 24 hours
    default_max_memory_messages: int = 10

    # Rate Limiting (requests per minute/hour)
    rate_limit_rpm: int = 60  # 60 requests per minute
    rate_limit_rph: int = 1000  # 1000 requests per hour
    
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


settings = Settings()