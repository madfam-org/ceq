"""
ceq-api: Creative Entropy Quantized

The skunkworks terminal for the generative avant-garde.
Wrestling order from the chaos of latent space.
"""

import os

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
    health,
    intent,
    interest,
    jobs,
    outputs,
    printability,
    render,
    synthesis,
    templates,
    workflows,
)

# Initialize logging first
setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


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

    logger.info("ceq-api ready. Signal acquired.")

    yield

    # Shutdown
    await close_redis()
    await close_db()
    logger.info("ceq-api shutting down... Entropy released.")


app = FastAPI(
    title="ceq API",
    description="Creative Entropy Quantized - Workflow Orchestration API",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
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
app.include_router(interest.router)
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
