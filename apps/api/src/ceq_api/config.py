"""Configuration management for ceq-api."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "ceq-api"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 5800
    workers: int = 1

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://ceq:ceq_dev@localhost:5432/ceq_dev"
    )

    # Redis (DB 14 per PORT_ALLOCATION.md)
    redis_url: RedisDsn = Field(default="redis://localhost:6379/14")

    # Furnace (GPU compute)
    furnace_api_url: str = "http://localhost:4210"
    furnace_api_key: str = ""

    # Janua (authentication)
    janua_api_url: str = "http://localhost:4100"
    janua_enabled: bool = True

    # R2 Storage (Cloudflare)
    r2_endpoint: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = "ceq-assets"
    r2_public_url: str = ""

    # ComfyUI
    comfyui_default_timeout: int = 300  # 5 minutes
    comfyui_max_concurrent_jobs: int = 10

    # CORS
    cors_origins: list[str] = ["http://localhost:5801", "https://ceq.lol"]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
