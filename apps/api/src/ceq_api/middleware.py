"""Security and observability middleware for ceq-api."""

import logging
import time
from typing import Callable

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from ceq_api.config import get_settings
from ceq_api.logging import get_request_id, set_request_id

logger = logging.getLogger(__name__)
settings = get_settings()


def get_client_identifier(request: Request) -> str:
    """
    Get client identifier for rate limiting.

    Uses user ID if authenticated, otherwise falls back to IP address.
    """
    # Check for authenticated user (set by auth middleware)
    if hasattr(request.state, "user_id"):
        return f"user:{request.state.user_id}"

    # Check X-Forwarded-For for clients behind proxy
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return get_remote_address(request)


# Initialize rate limiter
limiter = Limiter(
    key_func=get_client_identifier,
    default_limits=["100/minute"],  # Default rate limit
    enabled=settings.is_production,  # Only enable in production
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Handle rate limit exceeded errors."""
    logger.warning(
        f"Rate limit exceeded for {get_client_identifier(request)}: {exc.detail}",
        extra={"path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Latent space overloaded. Too many requests. Please slow down.",
            "retry_after": exc.detail,
        },
        headers={"Retry-After": str(60)},  # Retry after 60 seconds
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Add correlation ID to all requests."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        # Check for existing request ID from client or generate new one
        request_id = request.headers.get("X-Request-ID") or set_request_id()
        set_request_id(request_id)

        # Store in request state for access in handlers
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing information."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        start_time = time.perf_counter()

        # Skip logging for health checks and metrics
        if request.url.path in ["/health", "/ready", "/metrics"]:
            return await call_next(request)

        # Log request
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client": get_client_identifier(request),
            },
        )

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log response
        log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            log_level,
            f"Request completed: {request.method} {request.url.path} -> {response.status_code} ({duration_ms:.2f}ms)",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy for API
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        # Prevent caching of sensitive data
        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent DoS attacks."""

    # Max 100MB for asset uploads, 1MB for other requests
    DEFAULT_MAX_SIZE = 1 * 1024 * 1024  # 1MB
    UPLOAD_MAX_SIZE = 100 * 1024 * 1024  # 100MB

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        # Determine max size based on endpoint
        if request.url.path.startswith("/v1/assets") and request.method == "POST":
            max_size = self.UPLOAD_MAX_SIZE
        else:
            max_size = self.DEFAULT_MAX_SIZE

        # Check Content-Length header
        content_length = request.headers.get("content-length")
        if content_length:
            if int(content_length) > max_size:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "detail": f"Request too large. Maximum size: {max_size / 1024 / 1024:.0f}MB"
                    },
                )

        return await call_next(request)


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the application."""
    # Add middleware in reverse order (last added = first executed)

    # Request size limit (outermost - reject large requests early)
    app.add_middleware(RequestSizeLimitMiddleware)

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Request logging (after request ID is set)
    app.add_middleware(RequestLoggingMiddleware)

    # Request ID (innermost - available to all other middleware)
    app.add_middleware(RequestIdMiddleware)

    # Rate limiting - handled by slowapi decorator on individual routes
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
