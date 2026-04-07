"""Configuration management for ceq-api."""

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


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
    janua_jwks_url: str = ""  # e.g. https://auth.madfam.io/.well-known/jwks.json
    janua_issuer: str = ""  # e.g. https://auth.madfam.io
    janua_audience: str = ""  # e.g. ceq-api

    # R2 Storage (Cloudflare)
    r2_endpoint: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = "ceq-assets"
    r2_public_url: str = ""

    # ComfyUI
    comfyui_default_timeout: int = 300  # 5 minutes
    comfyui_max_concurrent_jobs: int = 10

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_default: str = "100/minute"
    rate_limit_uploads: str = "10/minute"
    rate_limit_jobs: str = "30/minute"

    # Security
    max_request_size_mb: int = 1  # Default max request size
    max_upload_size_mb: int = 100  # Max upload size for assets
    presigned_url_expiry_seconds: int = 3600  # 1 hour

    # CORS
    cors_origins: list[str] = ["http://localhost:5801", "https://ceq.lol"]

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Validate required settings for production environment."""
        if self.environment == "production":
            errors = []

            # R2 Storage validation
            if not self.r2_endpoint:
                errors.append("R2_ENDPOINT is required in production")
            if not self.r2_access_key:
                errors.append("R2_ACCESS_KEY is required in production")
            if not self.r2_secret_key:
                errors.append("R2_SECRET_KEY is required in production")

            # Janua validation
            if self.janua_enabled and "localhost" in self.janua_api_url:
                errors.append("JANUA_API_URL cannot be localhost in production")

            # Database validation
            db_url = str(self.database_url)
            if "localhost" in db_url or "ceq_dev" in db_url:
                errors.append("DATABASE_URL appears to be a development URL")

            if errors:
                error_msg = "Production configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
                raise ValueError(error_msg)

        elif self.environment == "staging":
            # Warnings for staging
            if not self.r2_endpoint:
                logger.warning("R2_ENDPOINT not configured - storage features will be disabled")

        return self

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"

    @property
    def r2_configured(self) -> bool:
        """Check if R2 storage is configured."""
        return bool(self.r2_endpoint and self.r2_access_key and self.r2_secret_key)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
