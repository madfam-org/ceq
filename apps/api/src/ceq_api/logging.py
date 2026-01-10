"""Structured logging configuration for ceq-api."""

import logging
import sys
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from pythonjsonlogger import jsonlogger

from ceq_api.config import get_settings

# Context variable for request correlation ID
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with ceq-specific fields."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["service"] = "ceq-api"
        log_record["level"] = record.levelname
        log_record["timestamp"] = self.formatTime(record)
        log_record["request_id"] = getattr(record, "request_id", "-")

        # Add exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)


def generate_request_id() -> str:
    """Generate a unique request ID."""
    return uuid4().hex[:12]


def set_request_id(request_id: str | None = None) -> str:
    """Set the request ID for the current context."""
    rid = request_id or generate_request_id()
    request_id_ctx.set(rid)
    return rid


def get_request_id() -> str:
    """Get the current request ID."""
    return request_id_ctx.get() or "-"


def setup_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()

    # Determine log level
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    # Use JSON format in production, readable format in development
    if settings.is_production:
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s"
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    handler.addFilter(CorrelationIdFilter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = [handler]

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.debug else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)


# Audit logging for security-sensitive operations
class AuditLogger:
    """Logger for security-sensitive operations."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("ceq.audit")

    def log_auth_attempt(
        self,
        success: bool,
        user_id: str | None = None,
        email: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Log authentication attempt."""
        self.logger.info(
            "auth_attempt",
            extra={
                "event_type": "auth_attempt",
                "success": success,
                "user_id": user_id,
                "email": email,
                "reason": reason,
            },
        )

    def log_asset_operation(
        self,
        operation: str,
        asset_id: str,
        user_id: str,
        filename: str | None = None,
        success: bool = True,
        reason: str | None = None,
    ) -> None:
        """Log asset upload/delete operations."""
        self.logger.info(
            f"asset_{operation}",
            extra={
                "event_type": f"asset_{operation}",
                "asset_id": asset_id,
                "user_id": user_id,
                "filename": filename,
                "success": success,
                "reason": reason,
            },
        )

    def log_job_operation(
        self,
        operation: str,
        job_id: str,
        user_id: str,
        workflow_id: str | None = None,
        success: bool = True,
        reason: str | None = None,
    ) -> None:
        """Log job creation/cancellation."""
        self.logger.info(
            f"job_{operation}",
            extra={
                "event_type": f"job_{operation}",
                "job_id": job_id,
                "user_id": user_id,
                "workflow_id": workflow_id,
                "success": success,
                "reason": reason,
            },
        )

    def log_admin_action(
        self,
        action: str,
        admin_id: str,
        target_type: str,
        target_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log administrative actions."""
        self.logger.warning(
            f"admin_{action}",
            extra={
                "event_type": f"admin_{action}",
                "admin_id": admin_id,
                "target_type": target_type,
                "target_id": target_id,
                "details": details,
            },
        )


# Singleton audit logger
audit_logger = AuditLogger()
