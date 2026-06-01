"""
ceq-api: Creative Entropy Quantized

The skunkworks terminal for the generative avant-garde.
Wrestling order from the chaos of latent space.
"""

import asyncio
import os
from contextlib import suppress  # noqa: E402
from datetime import datetime, timedelta
from typing import Any

# Initialize Sentry early, before other imports
_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=_sentry_dsn,
            environment=os.environ.get("SENTRY_ENVIRONMENT", os.environ.get("APP_ENV", "development")),
            traces_sample_rate=0.1,
            integrations=[FastApiIntegration()],
        )
    except ImportError:
        pass  # sentry-sdk not installed

# Sentry init must happen BEFORE these imports — instruments FastAPI on import.
import logging  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from prometheus_client import make_asgi_app  # noqa: E402

from ceq_api.config import get_settings  # noqa: E402
from ceq_api.logging import setup_logging  # noqa: E402
from ceq_api.middleware import setup_middleware  # noqa: E402
from ceq_api.routers import (  # noqa: E402
    assets,
    credits,
    health,
    intent,
    interest,
    jobs,
    operations,
    outputs,
    printability,
    render,
    synthesis,
    templates,
    workflows,
)

_METRICS_COLLECTION_INTERVAL_SECONDS = int(
    os.environ.get("CEQ_METRICS_COLLECTION_INTERVAL_SECONDS", "30")
)

# Initialize logging first
setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()
show_docs = not settings.is_production


async def _safe_llen(redis: Any, key: str) -> int:
    """Read a Redis list length while ignoring transient cache failures."""
    try:
        return int(await redis.llen(key))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to read Redis list length for %s: %s", key, exc)
        return 0


async def _collect_runtime_metrics() -> None:
    """Refresh Prometheus gauges used by stability dashboards and alerts."""
    from ceq_api.metrics import (
        set_alembic_revision_health,
        set_completion_dead_letters,
        set_queue_depth,
        set_running_jobs_stale_1h,
    )

    try:
        from ceq_api.db.redis import get_redis
        from ceq_api.db.session import async_session_maker
        from ceq_api.models.job import Job, JobStatus
    except Exception as exc:  # noqa: BLE001
        logger.debug("Runtime metrics dependencies unavailable: %s", exc)
        return

    try:
        redis = get_redis()
        pending = await _safe_llen(redis, "ceq:jobs:pending")
        processing = await _safe_llen(redis, "ceq:jobs:processing")
        dead_letters = await _safe_llen(redis, settings.job_completion_dead_letter_key)

        set_queue_depth(pending=pending, processing=processing)
        set_completion_dead_letters(dead_letters)

        threshold = datetime.utcnow() - timedelta(hours=1)
        async with async_session_maker() as db:
            from sqlalchemy import func, select, text

            stale_result = await db.execute(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.status == JobStatus.RUNNING.value,
                    Job.started_at.is_not(None),
                    Job.started_at < threshold,
                )
            )
            stale_running = stale_result.scalar_one()

            revision_result = await db.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            revision_value = revision_result.scalar_one_or_none()

        set_running_jobs_stale_1h(int(stale_running or 0))
        set_alembic_revision_health(
            revision_value if isinstance(revision_value, str) else None
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Runtime metrics collection failed: %s", exc)


async def _run_observability_metrics_sampler() -> None:
    """Continuously refresh in-API stability gauges."""
    while True:
        await _collect_runtime_metrics()
        await asyncio.sleep(_METRICS_COLLECTION_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    logger.info("ceq-api starting... Quantizing entropy...")

    # Initialize database
    from ceq_api.db.redis import close_redis, init_redis
    from ceq_api.db.session import close_db, init_db

    await init_db()
    await init_redis()

    await _collect_runtime_metrics()
    metrics_task = asyncio.create_task(_run_observability_metrics_sampler())

    logger.info("ceq-api ready. Signal acquired.")

    yield

    metrics_task.cancel()
    with suppress(asyncio.CancelledError):
        await metrics_task

    # Shutdown
    await close_redis()
    await close_db()
    logger.info("ceq-api shutting down... Entropy released.")


app = FastAPI(
    title="ceq API",
    description="Creative Entropy Quantized - Workflow Orchestration API",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if show_docs else None,
    redoc_url="/redoc" if show_docs else None,
    openapi_url="/openapi.json" if show_docs else None,
)

# CORS (must be added before other middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# Setup security and observability middleware
setup_middleware(app)

# Prometheus metrics at /metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Routers
app.include_router(health.router, tags=["health"])
app.include_router(workflows.router, prefix="/v1/workflows", tags=["workflows"])
app.include_router(jobs.router, prefix="/v1/jobs", tags=["jobs"])
app.include_router(templates.router, prefix="/v1/templates", tags=["templates"])
app.include_router(assets.router, prefix="/v1/assets", tags=["assets"])
app.include_router(outputs.router, prefix="/v1/outputs", tags=["outputs"])
app.include_router(render.router, prefix="/v1/render", tags=["render"])
app.include_router(credits.router, prefix="/v1/credits", tags=["credits"])
app.include_router(interest.router)
app.include_router(operations.router, prefix="/v1/operations", tags=["operations"])
# Intelligence layer — CEQ Cognitive Reasoning
app.include_router(synthesis.router, prefix="/v1/synthesis", tags=["synthesis"])
app.include_router(printability.router, prefix="/v1/printability", tags=["printability"])
app.include_router(intent.router, prefix="/v1/intent", tags=["intent"])


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with ceq branding."""
    return {
        "service": "ceq-api",
        "tagline": "Creative Entropy Quantized",
        "status": "Signal acquired. 📡",
        "version": settings.app_version,
    }
