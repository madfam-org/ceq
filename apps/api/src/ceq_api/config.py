"""Configuration management for ceq-api."""

import logging
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
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

    # Database — typed `str` rather than `PostgresDsn` so test runs can pass
    # `sqlite+aiosqlite://` (PostgresDsn rejects non-postgres schemes).
    # Production URL format is still validated at startup by the Validation
    # check below (see `errors.append(...)` block below).
    database_url: str = Field(
        default="postgresql+asyncpg://ceq:ceq_dev@localhost:5432/ceq_dev"
    )
    # Connection budget vs the SHARED postgres.data.svc: max_connections=100
    # for the ENTIRE cluster, ~90 in use at steady state, and a cluster-wide
    # exhaustion incident on 2026-07-22. Budget for ceq-api: 2 replicas x
    # (pool 5 + overflow 5) = 20 absolute max against a measured steady state
    # of ~8. Raise per-env via DATABASE_POOL_SIZE / DATABASE_MAX_OVERFLOW
    # (no env prefix configured), not by editing code. (Same pattern as
    # fortuna and janua.)
    # Set when the runtime routes through pgbouncer (transaction pooling):
    # migrations (ArgoCD PreSync job -> alembic) must keep a DIRECT postgres
    # connection. Unset => alembic uses database_url (direct deployments
    # unchanged).
    direct_database_url: str | None = Field(default=None)
    database_pool_size: int = Field(default=5)
    database_max_overflow: int = Field(default=5)

    # Redis (DB 14 per PORT_ALLOCATION.md)
    redis_url: RedisDsn = Field(default="redis://localhost:6379/14")

    # Furnace (GPU compute)
    furnace_api_url: str = "http://localhost:4210"
    furnace_api_key: str = ""

    # Janua (authentication)
    janua_api_url: str = Field(
        default="http://localhost:4100",
        validation_alias=AliasChoices("JANUA_API_URL", "JANUA_URL"),
    )
    janua_enabled: bool = True
    janua_jwks_url: str = Field(
        default="",
        validation_alias=AliasChoices("JANUA_JWKS_URL", "JANUA_PUBLIC_JWKS_URL"),
    )  # e.g. https://auth.madfam.io/.well-known/jwks.json
    janua_issuer: str = Field(
        default="",
        validation_alias=AliasChoices("JANUA_ISSUER", "JANUA_ISSUER_URL"),
    )  # e.g. https://auth.madfam.io
    janua_audience: str = Field(
        default="",
        validation_alias=AliasChoices("JANUA_AUDIENCE", "JANUA_AUDIENCE_ID"),
    )  # e.g. ceq-api

    # Janua service principals (client_credentials / machine-to-machine).
    #
    # Batch and machine callers cannot hold a browser session, so they mint a
    # short-lived RS256 token from Janua's `client_credentials` grant (ADR-006,
    # the same edge pattern as fashion-cabinet -> yantra4d). Those tokens carry
    # `token_use: "client_credentials"`, `sub: "service-account:<client_id>"`
    # (NOT a user UUID), `actor_type: "service_account"` and a `scope` string.
    #
    # A service token is accepted only when it carries `service_principal_scope`
    # AND its audience matches `janua_audience` (audience validation happens in
    # the normal JWKS decode). Set `service_principals_enabled=False` to hard-off
    # the whole path — human-user auth is unaffected either way.
    service_principals_enabled: bool = True
    service_principal_scope: str = Field(
        default="ceq:render",
        validation_alias=AliasChoices(
            "SERVICE_PRINCIPAL_SCOPE", "CEQ_SERVICE_PRINCIPAL_SCOPE"
        ),
    )

    # R2 Storage (Cloudflare)
    r2_endpoint: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = Field(
        default="ceq-assets",
        validation_alias=AliasChoices("R2_BUCKET", "R2_BUCKET_NAME"),
    )
    r2_public_url: str = ""

    # ComfyUI
    comfyui_default_timeout: int = 300  # 5 minutes
    comfyui_max_concurrent_jobs: int = 10
    max_active_jobs_per_user: int = 5
    max_active_jobs_pro: int = 10
    max_active_jobs_studio: int = 25
    max_active_jobs_admin: int = 0

    # Commercial metering
    render_credit_debits_enabled: bool = False
    render_credit_cost_card: int = 5
    render_credit_cost_audio: int = 3
    render_credit_cost_3d: int = 10
    gpu_job_credit_debits_enabled: bool = False
    gpu_job_credit_cost_image: int = 25
    gpu_job_credit_cost_video: int = 75
    gpu_job_credit_cost_3d: int = 50
    gpu_job_credit_cost_default: int = 25

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_default: str = "100/minute"
    rate_limit_uploads: str = "10/minute"
    rate_limit_jobs: str = "30/minute"
    # Service principals get their OWN limiter bucket, keyed by client_id, so a
    # 720-object backfill cannot starve human users out of the shared default
    # bucket. The global per-identity default (100/minute) still applies on top;
    # this is the ceiling for the service identity specifically.
    rate_limit_service_principal: str = "100/minute"

    # Security
    max_request_size_mb: int = 1  # Default max request size
    max_upload_size_mb: int = 100  # Max upload size for assets
    presigned_url_expiry_seconds: int = 3600  # 1 hour

    # Worker callback channel
    job_completion_callback_token: str = ""
    job_completion_callback_path: str = "/v1/jobs/{job_id}/outputs/report"
    job_completion_callback_timeout_seconds: float = 5.0
    job_completion_dead_letter_key: str = "ceq:jobs:completion:dead"

    # User job completion webhooks
    job_webhook_secret: str = ""
    job_webhook_timeout_seconds: float = 5.0
    job_webhook_max_attempts: int = 3
    job_webhook_retry_backoff_seconds: float = 1.0

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5800",
        "http://localhost:5801",
        "https://ceq.lol",
        "https://app.ceq.lol",
    ]

    # InterestGate / pre-monetization feature-interest capture
    # When `interest_enabled=True` (default), the public POST /v1/interest/
    # endpoint accepts email + feature_key submissions from the studio's
    # InterestGate component. Set to False to hard-disable capture (the
    # endpoint will return 503).
    interest_enabled: bool = True

    # Public landing demo — rate-limited /v1/demo/* renders without auth/credits.
    demo_enabled: bool = True

    # Outbound webhook to Phynd-CRM. When CRM_WEBHOOK_URL is empty the
    # `dispatch_interest_to_crm` background task is a no-op — the row is still
    # persisted, we just skip the push. Set both values to wire CRM sync.
    crm_webhook_url: str = ""
    crm_webhook_secret: str = ""
    crm_webhook_timeout_seconds: float = 5.0

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

            if not self.job_completion_callback_token:
                errors.append(
                    "JOB_COMPLETION_CALLBACK_TOKEN is required in production"
                )

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
