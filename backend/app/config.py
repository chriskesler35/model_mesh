"""Application configuration using Pydantic Settings."""

import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database - default to SQLite for local dev, Postgres for production
    database_url: str = "sqlite+aiosqlite:///:memory:"
    
    # Redis - optional for local dev
    redis_url: Optional[str] = None
    
    # API Keys (from environment, never stored in DB)
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    # ComfyUI for image generation
    comfyui_url: str = "http://localhost:8188"
    
    # Application
    modelmesh_api_key: str = "modelmesh_local_dev_key"
    ollama_base_url: str = "http://localhost:11434"
    
    # Memory
    memory_ttl_seconds: int = 86400  # 24 hours
    default_max_memory_messages: int = 10

    # Rate Limiting (requests per minute/hour)
    rate_limit_rpm: int = 60  # 60 requests per minute
    rate_limit_rph: int = 1000  # 1000 requests per hour
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()