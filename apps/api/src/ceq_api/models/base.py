"""Base model with common fields for all database models."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, TypeDecorator, func
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, String


class JSONB(TypeDecorator):
    """
    Platform-agnostic JSONB type.

    Uses PostgreSQL's JSONB when available, falls back to JSON for SQLite.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())
        return dialect.type_descriptor(JSON())


class GUIDString(TypeDecorator):
    """
    Platform-agnostic UUID type.

    Uses PostgreSQL's UUID when available, falls back to String for SQLite.
    """

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is not None:
            if dialect.name == "postgresql":
                return value
            return str(value) if isinstance(value, UUID) else value
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is not None:
            if isinstance(value, UUID):
                return value
            return UUID(value)
        return value


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""

    id: Mapped[UUID] = mapped_column(
        GUIDString(),
        primary_key=True,
        default=uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
