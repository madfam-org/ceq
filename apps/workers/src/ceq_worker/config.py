"""Configuration for ceq-worker."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Worker settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )

    # Worker identity
    worker_id: str = Field(default="ceq-worker-1")
    worker_type: str = "comfyui"

    # Paths
    comfyui_path: Path = Field(default=Path("/opt/comfyui"))
    models_path: Path = Field(default=Path("/opt/models"))
    outputs_path: Path = Field(default=Path("/opt/outputs"))
    cache_path: Path = Field(default=Path("/opt/cache"))

    # Redis (DB 14 per PORT_ALLOCATION.md)
    redis_url: RedisDsn = Field(default="redis://localhost:6379/14")
    worker_redis_url: str = Field(
        default="",
        validation_alias=AliasChoices("CEQ_WORKER_REDIS_URL", "WORKER_REDIS_URL"),
    )
    job_queue_key: str = "ceq:jobs:pending"
    job_processing_key: str = "ceq:jobs:processing"
    job_results_key: str = "ceq:jobs:results"

    # API
    api_url: str = "http://localhost:5800"
    worker_api_url: str = Field(
        default="",
        validation_alias=AliasChoices("CEQ_WORKER_API_URL", "WORKER_API_URL"),
    )
    api_job_completion_path: str = "/v1/jobs/{job_id}/outputs/report"
    api_job_completion_token: str = ""
    api_job_completion_timeout_seconds: float = 5.0
    api_job_completion_max_attempts: int = 3
    api_job_completion_retry_backoff_seconds: float = 1.0
    job_completion_dead_letter_key: str = "ceq:jobs:completion:dead"

    # --- Lease mode (HTTPS job pull) -------------------------------------
    #
    # When `lease_url` AND the service credentials are set, `ceq-worker` pulls
    # jobs from `POST {lease_url}/v1/worker/lease` over authenticated HTTPS
    # instead of connecting to Redis. This is what lets a Vast.ai instance run
    # without `ceq:jobs:pending` being exposed on the public internet.
    #
    # Redis mode remains the DEFAULT and is completely untouched: an in-cluster
    # worker with no CEQ_LEASE_URL behaves exactly as before.
    lease_url: str = Field(
        default="",
        validation_alias=AliasChoices("CEQ_LEASE_URL", "LEASE_URL"),
    )
    # Janua confidential client used to mint the `ceq:worker` token. This is a
    # DIFFERENT client from any `ceq:render` batch driver — executing jobs and
    # submitting jobs are separate capabilities.
    janua_token_url: str = Field(
        default="https://auth.madfam.io/api/v1/oauth/token",
        validation_alias=AliasChoices("CEQ_JANUA_TOKEN_URL", "JANUA_TOKEN_URL"),
    )
    janua_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("CEQ_WORKER_CLIENT_ID", "JANUA_CLIENT_ID"),
    )
    janua_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices("CEQ_WORKER_CLIENT_SECRET", "JANUA_CLIENT_SECRET"),
    )
    janua_scope: str = Field(
        default="ceq:worker",
        validation_alias=AliasChoices("CEQ_WORKER_SCOPE", "JANUA_SCOPE"),
    )
    janua_audience: str = Field(
        default="",
        validation_alias=AliasChoices("CEQ_WORKER_AUDIENCE", "JANUA_AUDIENCE"),
    )
    # Re-mint this many seconds BEFORE `exp` so a long request never starts with
    # a token that expires mid-flight.
    token_refresh_leeway_seconds: int = 60
    # Idle backoff between empty lease polls (the API answers 204 immediately;
    # this is what stops an empty queue becoming a hot loop).
    lease_poll_interval_seconds: float = 5.0
    lease_request_timeout_seconds: float = 30.0
    # Requested visibility timeout. The API clamps this to its own ceiling.
    lease_ttl_seconds: int = 300
    # Heartbeat cadence is taken from the API's response; this is the fallback
    # when the response omits it.
    lease_heartbeat_interval_seconds: int = 60

    # R2 Storage
    r2_endpoint: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = Field(
        default="ceq-assets",
        validation_alias=AliasChoices("R2_BUCKET", "R2_BUCKET_NAME"),
    )
    r2_public_url: str = ""

    # GPU
    gpu_device: str = "cuda:0"
    vram_limit_gb: float = 20.0  # RTX 4000 SFF Ada

    # Execution
    default_timeout: int = 300  # 5 minutes
    max_concurrent_nodes: int = 1
    enable_previews: bool = True

    # Health
    health_check_interval: int = 30

    # GPU Provider Configuration
    gpu_provider: Literal["vast", "fal", "furnace"] = Field(default="vast")

    # Vast.ai Configuration (instance-based, Docker deployment)
    vast_api_key: str = Field(default="")
    vast_region: str = Field(default="any")
    vast_ssh_key: str = Field(default="~/.ssh/id_rsa")
    vast_max_price: float = Field(default=1.0)  # $/hr
    vast_max_instances: int = Field(default=5)

    # fal.ai Configuration (serverless API, per-request billing)
    fal_api_key: str = Field(default="")
    fal_max_hourly_spend: float = Field(default=5.0)  # $/hr budget cap

    # Furnace Configuration (future - Enclii internal)
    furnace_api_key: str = Field(default="")
    furnace_api_url: str = Field(default="http://furnace-gateway:4210")
    furnace_region: str = Field(default="hetzner-fsn1")

    # Orchestrator Configuration
    ceq_min_workers: int = Field(default=0)
    ceq_max_workers: int = Field(default=5)
    ceq_scale_up_threshold: int = Field(default=5)
    ceq_scale_down_threshold: int = Field(default=0)
    ceq_idle_timeout: int = Field(default=300)
    ceq_max_hourly_spend: float = Field(default=5.0)

    @property
    def external_worker_redis_url(self) -> str:
        """Redis URL injected into external GPU workers (Vast.ai, etc.)."""
        return self.worker_redis_url or str(self.redis_url)

    @property
    def external_worker_api_url(self) -> str:
        """API URL reachable from external GPU workers."""
        return self.worker_api_url or self.api_url

    @property
    def lease_mode_enabled(self) -> bool:
        """Whether this worker should pull jobs over HTTPS instead of Redis.

        All three of URL + client id + secret are required: a half-configured
        lease setup must fall back to Redis mode loudly rather than silently
        starting a worker that can never authenticate.
        """
        return bool(self.lease_url and self.janua_client_id and self.janua_client_secret)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
