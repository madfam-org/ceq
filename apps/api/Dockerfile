# CEQ API - FastAPI Orchestration Service
#
# Multi-stage build for production deployment.
#
# Build:
#   docker build -t ceq-api:latest .
#
# Run:
#   docker run -p 5800:5800 ceq-api:latest

# =============================================================================
# Stage 1: Build dependencies
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir build hatchling && \
    pip install --no-cache-dir .

# =============================================================================
# Stage 2: Production image
# =============================================================================
FROM python:3.11-slim AS production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    fonts-dejavu-core \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash ceq

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=ceq:ceq src/ ./src/
COPY --chown=ceq:ceq alembic.ini ./

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV ENVIRONMENT=production

# Expose API port
EXPOSE 5800

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:5800/health || exit 1

# Switch to non-root user
USER ceq

# Run with uvicorn
CMD ["uvicorn", "ceq_api.main:app", "--host", "0.0.0.0", "--port", "5800", "--workers", "2"]
