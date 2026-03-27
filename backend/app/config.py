"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    database_url: str = "postgresql+asyncpg://modelmesh:modelmesh@localhost:5432/modelmesh"
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    # API Keys (from environment, never stored in DB)
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    
    # Application
    modelmesh_api_key: str = "modelmesh_local_dev_key"
    ollama_base_url: str = "http://localhost:11434"
    
    # Memory
    memory_ttl_seconds: int = 86400  # 24 hours
    default_max_memory_messages: int = 10
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()