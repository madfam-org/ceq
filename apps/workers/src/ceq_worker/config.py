"""Configuration for ceq-worker."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Worker settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
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
    job_queue_key: str = "ceq:jobs:pending"
    job_processing_key: str = "ceq:jobs:processing"
    job_results_key: str = "ceq:jobs:results"

    # API
    api_url: str = "http://localhost:5800"

    # R2 Storage
    r2_endpoint: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = "ceq-assets"
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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
